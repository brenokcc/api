# -*- coding: utf-8 -*-
import os
import time
import sys
import datetime
import traceback
import unicodedata
from selenium import webdriver
from django.conf import settings
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import WebDriverException, StaleElementReferenceException


def normalize(name):
    if 'api.middleware.ReactJsMiddleware' in settings.MIDDLEWARE:
        return unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode().lower().replace('-', '').replace('_', '')
    return name


class Browser(webdriver.Firefox):
    
    def __init__(self, server_url, options=None, verbose=True, slowly=False, maximize=True, headless=True):
        if not options:
            options = Options()
        if maximize:
            options.add_argument("--start-maximized")
        else:
            options.add_argument("--window-size=720x800")
        if headless and '-v' not in sys.argv:
            options.add_argument("--headless")

        super().__init__(options=options)

        self.cursor = None
        self.verbose = verbose
        self.slowly = slowly
        self.server_url = server_url
        self.headless = headless

        if maximize:
            self.maximize_window()
        else:
            self.set_window_position(700, 0)
            self.set_window_size(720, 800)
        self.switch_to.window(self.current_window_handle)

    def slow(self, slowly=True):
        self.slowly = slowly

    def wait_start(self):
        for i in range(0, 5):
            print('Waiting for process to starting ({}s)....'.format(i))
            try:
                if not [el for el in self.find_elements('css selector', '.btn') if 'Aguarde...' in el.text]:
                    self.wait()
            except StaleElementReferenceException:
                print('Exception!')
                self.wait()

    def wait_finish(self):
        for i in range(0, 60):
            print('Waiting for process to finish ({}s)....'.format(i))
            try:
                if [el for el in self.find_elements('css selector', '.btn') if 'Aguarde...' in el.text]:
                    self.wait()
                else:
                    break
            except StaleElementReferenceException:
                print('Exception!')
                break

    def is_cursor_inside(self, tag_name):
        if self.cursor:
            if self.cursor.tag_name == tag_name:
                self.debug('Cursor {} is inside {}'.format(self.cursor.tag_name, tag_name))
                return True
            elif self.cursor.tag_name == 'html':
                self.debug('Cursor {} is NOT inside {}'.format(self.cursor.tag_name, tag_name))
                return False
            else:
                parent = self.cursor.find_element('xpath', '..')
                while True:
                    self.debug('Checking {}'.format(parent.tag_name))
                    if parent.tag_name == tag_name:
                        self.debug('Cursor {} is inside {}'.format(self.cursor.tag_name, tag_name))
                        return True
                    elif parent.tag_name == 'html':
                        return False
                    else:
                        parent = parent.find_element('xpath', '..')
        self.debug('Cursor {} is NOT inside {}'.format(self.cursor.tag_name, tag_name))
        return False

    def initialize_cursor(self):
        try:
            dialogs = super().find_elements(By.TAG_NAME, 'dialog')
            if dialogs:
                if self.cursor is None or not self.is_cursor_inside('dialog'):
                    self.cursor = dialogs[0]
            else:
                if self.cursor is None or not self.is_cursor_inside('html'):
                    self.cursor = super().find_element(By.TAG_NAME, 'html')
            self.cursor.tag_name
        except StaleElementReferenceException:
            self.cursor = super().find_element(By.TAG_NAME, 'html')
        self.debug('Cursor is at tag {}'.format(self.cursor.tag_name))

    def find_elements(self, by, value):
        self.initialize_cursor()
        while True:
            elements = self.cursor.find_elements(by, value)
            if elements:
                self.debug('Element {} found in {}.'.format(value, self.cursor.tag_name))
                return elements
            elif self.cursor.tag_name == 'dialog':
                self.debug('Recursive search stopped inside dialog!')
                break
            if self.cursor.tag_name != 'html':
                self.debug('Element {} not found in {}. Searching in the parent element...'.format(value, self.cursor.tag_name))
                self.cursor = self.cursor.find_element('xpath', '..')
        return []

    def find_element(self, by, value):
        self.initialize_cursor()
        while True:
            elements = self.cursor.find_elements(by, value)
            if elements:
                self.debug('Element {} found in {}.'.format(value, self.cursor.tag_name))
                return elements[0]
            elif self.cursor.tag_name == 'dialog':
                self.debug('Recursive search stopped inside dialog!')
                raise WebDriverException('Element {} not found in the dialog.'.format(value))
            if self.cursor.tag_name != 'html':
                self.debug('Element {} not found in {}. Searching in the parent element...'.format(value, self.cursor.tag_name))
                self.cursor = self.cursor.find_element('xpath', '..')

    def wait(self, seconds=1):
        time.sleep(seconds)

    def watch(self, e):
        self.save_screenshot('/tmp/test.png')
        if self.headless:
            raise e
        else:
            breakpoint()

    def print(self, message):
        if self.verbose:
            print(message)

    def debug(self, message):
        # print(message)
        pass

    def execute_script(self, script, *args):
        super().execute_script(script, *args)
        if self.slowly:
            self.wait(3)

    def open(self, url):
        if url.startswith('http'):
            self.get(url.replace('http://localhost:8000', self.server_url))
        else:
            self.get("{}{}".format(self.server_url, url))

    def reload(self):
        self.open(self.current_url)

    def enter(self, name, value, submit=False, count=4):
        if callable(value):
            value = value()
        if type(value) == datetime.date:
            value = value.strftime('%Y-%d-%m')
        self.print('{} "{}" for "{}"'.format('Entering', value, name))
        if value:
            value = str(value)
            if len(value) == 10 and value[2] == '/' and value[5] == '/':
                value = datetime.datetime.strptime(value, '%d/%m/%Y').strftime('%Y-%m-%d')
        try:
            widget = self.find_element(By.CSS_SELECTOR, '.form-control[data-label="{}"]'.format(normalize(name)))
            if widget.tag_name == 'input' and widget.get_property('type') == 'file':
                value = os.path.join(settings.BASE_DIR, value)
            widget.clear()
            widget.send_keys(value)
        except WebDriverException as e:
            if count:
                self.wait()
                self.enter(name, value, submit, count - 1)
            else:
                self.watch(e)
        if self.slowly:
            self.wait(2)

    def choose(self, name, value, count=4):
        self.print('{} "{}" for "{}"'.format('Choosing', value, name))
        try:
            widgets = self.find_elements(By.CSS_SELECTOR, '.form-control[data-label="{}"]'.format(normalize(name)))
            if widgets:
                if widgets[0].tag_name.lower() == 'select':
                    select = Select(widgets[0])
                    select.select_by_visible_text(value)
                elif widgets[0].tag_name.lower() == 'input':
                    widgets[0].send_keys(value)
                    for i in range(0, 6):
                        # print('Trying ({}) click at "{}"...'.format(i, value))
                        self.wait(0.5)
                        try:
                            super().find_element(By.CSS_SELECTOR, '.autocomplete-item[data-label*="{}"]'.format(normalize(value))).click()
                            break
                        except WebDriverException:
                            pass
            else:
                self.look_at(normalize(name))
                inputs = self.find_elements(By.CSS_SELECTOR, 'input[data-label="{}"]'.format(normalize(value)))
                if inputs:
                    if inputs[0].get_dom_attribute('type') == 'radio':
                        inputs[0].click()
                    elif inputs[0].get_dom_attribute('type') == 'checkbox':
                        inputs[0].click()
        except WebDriverException as e:
            if count:
                self.wait()
                self.choose(name, value, count - 1)
            else:
                self.watch(e)
        if self.slowly:
            self.wait(2)

    def dont_see_error_message(self, testcase=None):
        elements = self.find_elements(By.CLASS_NAME, 'alert-danger')
        if elements:
            messages = [element.text for element in elements]
            if True:
                input('Type enter to continue...')
            elif testcase:
                exception_message = 'The following messages were found on the page: {}'.format(';'.join(messages))
                raise testcase.failureException(exception_message)

    def see(self, text, flag=True, count=4):
        if flag:
            self.print('See "{}"'.format(text))
            try:
                assert text in self.find_element(By.TAG_NAME, 'body').text
            except AssertionError as e:
                if count:
                    self.wait()
                    self.see(text, flag, count - 1)
                else:
                    self.watch(e)
            if self.slowly:
                self.wait(2)
        else:
            self.print('Can\'t see "{}"'.format(text))
            try:
                assert text not in self.find_element(By.TAG_NAME, 'body').text
            except AssertionError as e:
                if count:
                    self.wait()
                    self.see(text, flag, count - 1)
                else:
                    self.watch(e)
            if self.slowly:
                self.wait(2)

    def see_message(self, text, count=4):
        self.print('See message "{}"'.format(text))
        try:
            pass
        except WebDriverException as e:
            if count:
                self.wait()
                self.see_message(text, count - 1)
            else:
                self.watch(e)
        if self.slowly:
            self.wait(2)

    def see_dialog(self, count=4):
        self.print('Looking at popup window')
        try:
            pass
        except WebDriverException as e:
            if count:
                self.wait()
                self.look_at_popup_window(count - 1)
            else:
                self.watch(e)
        if self.slowly:
            self.wait(2)

    def look_at(self, text, count=4):
        self.print('Loking at "{}"'.format(text))
        try:
            self.cursor = self.find_element(By.CSS_SELECTOR, '[data-label="{}"]'.format(normalize(text)))
            if self.cursor:
                self.execute_script("arguments[0].scrollIntoView();", self.cursor)
                self.debug('Cursor is now at {}'.format(self.cursor.tag_name))
        except WebDriverException as e:
            if count:
                self.wait()
                self.look_at(text, count - 1)
            else:
                self.watch(e)
        if self.slowly:
            self.wait(2)


    def search_menu(self, text, count=4):
        self.print('Searching "{}"'.format(text))
        try:
            self.enter('Buscar...', text)
            self.wait()
            self.click(text)
        except WebDriverException as e:
            if count:
                self.wait()
                self.search_menu(text, count=count - 1)
            else:
                self.watch(e)
        self.wait()

    def click_cell(self, i, j, checkbox=False, count=4):
        self.print('Clicking cell "{} x {}"'.format(i, j))
        try:
            trs = self.find_elements(By.CSS_SELECTOR, 'tbody > tr')
            if trs:
                tds = trs[i].find_elements(By.TAG_NAME, 'td')
                tds[j].find_element(By.CSS_SELECTOR, 'input[type=checkbox]').click() if checkbox else tds[j].click()
            else:
                self.wait()
                self.click_cell(i, j, checkbox=checkbox, count=count - 1)
        except WebDriverException as e:
            if count:
                self.wait()
                self.click_cell(i, j, checkbox=checkbox, count=count - 1)
            else:
                self.watch(e)

    def check_cell(self, i, j):
        self.click_cell(i, j, checkbox=True)

    def click(self, text, count=4):
        self.execute_script('hideMessage()');
        self.print('Clicking "{}"'.format(text))
        try:
            element = self.find_element(By.CSS_SELECTOR, '[data-label="{}"]'.format(normalize(text)))
            children = element.find_elements('css selector', 'i')
            if children:
                children[0].click()
            else:
                element.click()
        except WebDriverException as e:
            if count:
                self.wait()
                self.click(text, count=count - 1)
            else:
                self.watch(e)

    def logout(self, current_username):
        self.print('Logging out')
        self.click(current_username)
        self.click('Sair')

    def close(self, seconds=0):
        self.wait(seconds)
        super().close()
