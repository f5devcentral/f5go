#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import unittest
import time

import go


class GeneralTestCases(unittest.TestCase):
    def test_deampify_url(self):
        """
        Verify that ampersands are turned from '&amp;' to '&'
        :return:
        """
        input_string = 'https://www.example.com/webhp?sourceid=chrome-instant&amp;ion=1&amp;espv=2&amp;ie=UTF-8'
        expected = 'https://www.example.com/webhp?sourceid=chrome-instant&ion=1&espv=2&ie=UTF-8'
        self.assertEqual(expected, go.deampify(input_string))

    def test_prettyday_should_return_never(self):
        """
        Verify cases where the prettyday function should return the string 'never'
        :return:
        """
        self.assertEqual('never', go.prettyday(0))
        self.assertEqual('never', go.prettyday(-1))

    def test_prettyday_should_return_today(self):
        """
        Verify case where the prettyday function should return the string 'today'
        :return:
        """
        _today = go.today()
        self.assertEqual('today', go.prettyday(_today))

    def test_prettyday_should_return_yesterday(self):
        """
        Verify case where the prettyday function should return the string 'yesterday'
        :return:
        """
        yesterday = go.today() - 1
        self.assertEqual('yesterday', go.prettyday(yesterday))

    def test_prettyday_should_return_num_of_days(self):
        """
        Verify cases where the prettyday function should return the string for the number of days
        :return:
        """
        today = go.today()
        month_ago = today - 30
        self.assertEqual('30 days ago', go.prettyday(month_ago))

    def test_prettyday_should_return_num_of_months(self):
        """
        Verify cases where the prettyday function should return the string for the number of months
        :return:
        """
        today = go.today()
        months_ago = today - 95
        self.assertEqual('3 months ago', go.prettyday(months_ago))

    def test_prettytime_should_return_never(self):
        """
        Verify cases where the prettytime function should return the string 'never'
        :return:
        """
        self.assertEqual('never', go.prettytime(420))
        self.assertEqual('never', go.prettytime(-1))

    def test_prettytime_should_return_today(self):
        """
        Verify case where the prettytime function should return the string 'today'
        :return:
        """
        timestamp = time.time()
        self.assertEqual('today', go.prettytime(timestamp))

    def test_prettytime_should_return_yesterday(self):
        """
        Verify case where the prettytime function should return the string 'yesterday'
        :return:
        """
        timestamp = time.time() - (24 * 3600)
        self.assertEqual('yesterday', go.prettytime(timestamp))

    def test_prettytime_should_return_num_of_days(self):
        """
        Verify case where the prettytime function should return the string number of days
        :return:
        """
        timestamp = time.time() - (6 * 24 * 3600)
        self.assertEqual('6 days ago', go.prettytime(timestamp))

    def test_prettytime_should_return_num_of_months(self):
        """
        Verify case where the prettytime function should return the string number of months
        :return:
        """
        timestamp = time.time() - (95 * 24 * 3600)
        self.assertEqual('3 months ago', go.prettytime(timestamp))

    def test_should_return_true_for_int(self):
        self.assertTrue(go.is_int(5))

    def test_should_return_false_for_int(self):
        self.assertFalse(go.is_int('foo'))

    def test_makeList_should_return_list(self):
        """
        Verify that the makeList function returns a list of the items passed in using various data structures
        :return:
        """
        _list = [1, 2, 3]
        # Leave as an explicit set call to support python 2.6
        _num_set = set([42, 35])
        _string = 'foo'

        self.assertTrue(isinstance(go.makeList(_list), list))
        self.assertTrue(isinstance(go.makeList(_string), list))
        self.assertTrue(isinstance(go.makeList(_num_set), list))

        self.assertEqual(go.makeList(_list), _list)
        self.assertNotEqual(go.makeList(_string), _string)
        self.assertNotEqual(go.makeList(_num_set), _num_set)

    def test_escapekeyword_should_replace_singlequote(self):
        """
        %27 (as seen in expected) is the character used in web
        applications for a single quote
        """
        keyword = "\'test\'"
        expected = "%27test%27"
        self.assertEqual(expected, go.escapekeyword(keyword))

    def test_canonicalUrl_should_return_none(self):
        """
        When None is passed in None should be returned
        :return:
        """
        self.assertEqual(None, go.canonicalUrl(None))

    def test_canonicalUrl_should_return_correct_url(self):
        url = "https://www.google.com"
        self.assertEqual(url, go.canonicalUrl(url))

        # Validates that jinja2.utils.urlize works the way we expect
        url = "(https://www.google.com....."
        self.assertEqual("https://www.google.com", go.canonicalUrl(url))

    def test_sanitary_should_return_None(self):
        """
        Verify that underscores are marked as unsanitary charachters
        :return:
        """
        # While in theory underscores are fine, we block them as unsanitary
        url = "this_is_an_invalid_name"
        self.assertEqual(None, go.sanitary(url))

        # There's a branch that specifically checks the last character is valid or /
        url = "this-is-an-invalid-name_"
        self.assertEqual(None, go.sanitary(url))

    def test_sanitary_should_return_url(self):
        """
        Verify that dashes and / are considered sanitary characters
        :return:
        """
        url = "this-is-a-valid-name"
        self.assertEqual(url, go.sanitary(url))

        url = "this-is-a-valid-name/"
        self.assertEqual(url, go.sanitary(url))

    def test_getSSOUsername_should_return_testuser(self):
        # TODO: Will have to be changed if/when SSO is made generic
        self.assertEqual("testuser", go.getSSOUsername())


class LinkTestCases(unittest.TestCase):
    def test_create_link(self):
        link = go.Link(url='www.example.com', title='example site')
        self.assertEqual(0, link.linkid)
        self.assertEqual('example site', link.title)

    def test_edit_link(self):
        """
        Validate the last edit user starts off blank and then adds a users when edited
        :return:
        """
        link = go.Link(url='example.com', title='example site')
        (last_edit_time, last_edit_name) = link.lastEdit()
        self.assertEqual(0, last_edit_time)
        self.assertEqual('', last_edit_name)

        link.editedBy('testuser')
        (_, last_edit_name) = link.lastEdit()
        self.assertEqual('testuser', last_edit_name)

    def test_opacity_never_clicked(self):
        """
        By default the opacity is 0.2
        :return:
        """
        link = go.Link(url='example.com', title='example site')
        today = datetime.date.today()
        date = datetime.date.toordinal(today)
        self.assertEqual('0.20', link.opacity(date))

    def test_opacity_clicked_today(self):
        """
        By default the opacity is 0.2, by "clicking" today it's set to 1.0
        :return:
        """
        link = go.Link(url='example.com', title='example site')
        today = datetime.date.today()
        date = datetime.date.toordinal(today)
        link.clicked()
        self.assertEqual('1.00', link.opacity(date))

    def test_usage_not_exists(self):
        link = go.Link(url='example.com', title='example site')
        self.assertEqual('', link.usage())

if __name__ == '__main__':
    unittest.main()
