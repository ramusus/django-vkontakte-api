# -*- coding: utf-8 -*-
from django.test import TestCase
from parser import VkontakteParser

class VkontakteApiTest(TestCase):

    def test_parse_page(self):

        parser = VkontakteParser()
        parser.content = '<!><!><!><!><!><div>%s</div>' % '1<!-- ->->2<!-- -<>->3<!-- -->4'

        self.assertEqual(parser.html, '<div>1234</div>')