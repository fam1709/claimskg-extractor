# -*- coding: utf-8 -*-
from importlib.resources import contents
import re
from typing import List

import dateparser
from bs4 import BeautifulSoup, NavigableString
from tqdm import tqdm

from claim_extractor import Claim, Configuration, tag
from claim_extractor.extractors import FactCheckingSiteExtractor, caching


class DummyTag(object):
    def __init__(self):
        self.text = ""


class AosfatosFactCheckingSiteExtractor(FactCheckingSiteExtractor):

    def __init__(self, configuration: Configuration = Configuration(), ignore_urls: List[str] = None, headers=None,
                 language="pt"):
        super().__init__(configuration, ignore_urls, headers, language)

    def retrieve_listing_page_urls(self) -> List[str]:
        return ["https://www.aosfatos.org/noticias/checamos/?year=2022"]

    def find_page_count(self, parsed_listing_page: BeautifulSoup) -> int:
        curr_page = parsed_listing_page.select('div.pagination span a')
        max_page = curr_page[::-1][1].text.strip()

        return int(max_page)
        
    def retrieve_urls(self, parsed_listing_page: BeautifulSoup, listing_page_url: str, number_of_pages: int) \
            -> List[str]:
        urls = self.extract_urls(parsed_listing_page)
        for page_number in tqdm(range(2, number_of_pages)):
            if 0 < self.configuration.maxClaims < len(urls):
                break
            url = listing_page_url + "&page=" + str(page_number)
            page = caching.get(url, headers=self.headers, timeout=5)
            current_parsed_listing_page = BeautifulSoup(page, "lxml")
            urls = urls + self.extract_urls(current_parsed_listing_page)
        return urls

    def extract_urls(self, parsed_listing_page: BeautifulSoup):
        urls = list()
        links = parsed_listing_page.findAll("a", {"class": "entry-item-card"})
        
        for anchor in links:
            anchor =  anchor.attrs['href']
            url = 'https://www.aosfatos.org' + anchor
            max_claims = self.configuration.maxClaims
            if 0 < max_claims <= len(urls):
                break
            if url not in self.configuration.avoid_urls:
                urls.append(url)
        return urls

    def extract_claim_and_review(self, parsed_claim_review_page: BeautifulSoup, url: str) -> List[Claim]:
        claim = Claim()

        # url
        claim.url = str(url)

        # souce
        claim.source = "aosfatos"

        # title
        title = None
        if parsed_claim_review_page.select( 'article > h1' ):
            for tmp in parsed_claim_review_page.select( 'article > h1' ):
                title = tmp.text.strip()
            #sub_title = parsed_claim_review_page.select( 'article > header > h2' )
            claim.title = str(title.strip())

        # author 
        author_list = []
        author_links = []
        if parsed_claim_review_page.select( 'div.article-subtitle p' ):
           temp = parsed_claim_review_page.select( 'div.article-subtitle p' )
           author = temp[0].text
           claim.author = author[4:]
        else:
            claim.author = ''
        
        claim.author_url = "https://www.aosfatos.org/nossa-equipe/"
        # review_author ?
        # -
        
        # date
        datePub = None
        date_str = ""
        date_ = parsed_claim_review_page.select('div.article-subtitle div.publish-date')
        data = date_[0].text.replace('\n', '').replace(' ', '')
        claim.date = data
        # claim image?
        # -
        
        # claim
        claim_text = None
        if parsed_claim_review_page.select( 'blockquote' ) and not parsed_claim_review_page.select( 'blockquote.instagram-media' ):
            for t in parsed_claim_review_page.select( 'blockquote' ):
                text = t.text
                if text == ' ':
                    break
                claim.claim += text + '\n'

        # rating
        rating = None
        if parsed_claim_review_page.select('p.inline-stamp img'):
            for selo in parsed_claim_review_page.select('p.inline-stamp img'):
                normrating = selo.attrs['alt'][5:].capitalize()
                if normrating == "Falso":
                    claim.rating += "FALSE" + '\n'
                elif normrating == "Verdadeiro":
                    claim.rating = "TRUE" + '\n'
                else:
                    claim.rating = "MIXED" + '\n'

        
        # Body description
        footnote = 'Aos Fatos integra o Programa de Verificação de Fatos Independente da Meta. Veja aqui como funciona a parceria.'
        text = ""
        if parsed_claim_review_page.select( 'article > p' ):
            for child in parsed_claim_review_page.select( 'article > p' ):
                if not child.text or 'Referências:' in child.text or len(child.text) == 1 or '\n' in child.text or footnote in child.text: 
                    continue
                text += " " + child.text
            body_description = text.strip()
            claim.body = str(body_description).strip()

        # related links
        related_links = []
        links = []
        aux = parsed_claim_review_page.select('article > p')
        for el in aux:
            if type(el.next) is NavigableString and el.next.startswith('1.'):
                links = el
        if links:
            for link in links.select('a'):
                related_links.append(link.attrs['href'])

        claim.related_links = related_links
                
        # tags
        if parsed_claim_review_page.select( 'head > meta[name=keywords]'):
            keywrd = parsed_claim_review_page.select( 'head > meta[name=keywords]')
            a = keywrd[0]
            claim.tags = keywrd[0].attrs['content']

        #  No Rating? No Claim?
        if not claim.rating:
            print( url )
            if not claim.rating: 
                print ( "-> Rating cannot be found!" )
            return []
        if not claim.claim or claim.claim == ' \n':
            claim.claim = title
        

        claimtagged = tag.wat_entity_linking(claim.claim)
        tag.get_wat_annotations(claimtagged, claim)
        
        return [claim]