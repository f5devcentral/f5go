#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
import time

import go


class GeneralTestCases(unittest.TestCase):
    def test_deampify_url(self):
        input_string = 'https://www.example.com/webhp?sourceid=chrome-instant&amp;ion=1&amp;espv=2&amp;ie=UTF-8'
        expected = 'https://www.example.com/webhp?sourceid=chrome-instant&ion=1&espv=2&ie=UTF-8'
        self.assertEqual(expected, go.deampify(input_string))

    def test_prettyday_should_return_never(self):
        self.assertEqual('never', go.prettyday(0))
        self.assertEqual('never', go.prettyday(-1))

    def test_prettyday_should_return_today(self):
        _today = go.today()
        self.assertEqual('today', go.prettyday(_today))

    def test_prettyday_should_return_yesterday(self):
        yesterday = go.today() - 1
        self.assertEqual('yesterday', go.prettyday(yesterday))

    def test_prettyday_should_return_num_of_days(self):
        today = go.today()
        month_ago = today - 30
        self.assertEqual('30 days ago', go.prettyday(month_ago))

    def test_prettyday_should_return_num_of_months(self):
        today = go.today()
        months_ago = today - 95
        self.assertEqual('3 months ago', go.prettyday(months_ago))

    def test_prettytime_should_return_never(self):
        self.assertEqual('never', go.prettytime(420))
        self.assertEqual('never', go.prettytime(-1))

    def test_prettytime_should_return_today(self):
        timestamp = time.time()
        self.assertEqual('today', go.prettytime(timestamp))

    def test_prettytime_should_return_yesterday(self):
        timestamp = time.time() - (24 * 3600)
        self.assertEqual('yesterday', go.prettytime(timestamp))

    def test_prettytime_should_return_num_of_days(self):
        timestamp = time.time() - (6 * 24 * 3600)
        self.assertEqual('6 days ago', go.prettytime(timestamp))

    def test_prettytime_should_return_num_of_months(self):
        timestamp = time.time() - (95 * 24 * 3600)
        self.assertEqual('3 months ago', go.prettytime(timestamp))

    def test_should_return_true_for_int(self):
        self.assertTrue(go.is_int(5))

    def test_should_return_false_for_int(self):
        self.assertFalse(go.is_int('foo'))

    def test_makeList_should_return_list(self):
        _list = [1, 2, 3]
        _num_set = {42, 35}
        _string = 'foo'

        self.assertTrue(isinstance(go.makeList(_list), list))
        self.assertTrue(isinstance(go.makeList(_string), list))
        self.assertTrue(isinstance(go.makeList(_num_set), list))

        self.assertEqual(go.makeList(_list), _list)
        self.assertNotEqual(go.makeList(_string), _string)
        self.assertNotEqual(go.makeList(_num_set), _num_set)

    def test_escapekeyword_should_replace_singlequote(self):
        # %27 (as seen in expected) is the character used in web
        # applications for a single quote
        keyword = "\'test\'"
        expected = "%27test%27"
        self.assertEqual(expected, go.escapekeyword(keyword))

    def test_canonicalUrl_should_return_none(self):
        # When None is passed in None should be returned
        self.assertEqual(None, go.canonicalUrl(None))

    def test_canonicalUrl_should_return_correct_url(self):
        url = "https://www.google.com"
        self.assertEqual(url, go.canonicalUrl(url))

        # Validates that jinja2.utils.urlize works the way we expect
        url = "(https://www.google.com....."
        self.assertEqual("https://www.google.com", go.canonicalUrl(url))

    def test_sanitary_should_return_None(self):
        # While in theory underscores are fine, we block them as unsanitary
        url = "this_is_an_invalid_name"
        self.assertEqual(None, go.sanitary(url))

        # There's a branch that specifically checks the last character is valid or /
        url = "this-is-an-invalid-name_"
        self.assertEqual(None, go.sanitary(url))

    def test_sanitary_should_return_url(self):
        url = "this-is-a-valid-name"
        self.assertEqual(url, go.sanitary(url))

        url = "this-is-a-valid-name/"
        self.assertEqual(url, go.sanitary(url))

    def test_getSSOUsername_should_return_testuser(self):
        # Will have to be changed if/when SSO is made generic
        self.assertEqual("testuser", go.getSSOUsername())


if __name__ == '__main__':
    unittest.main()
