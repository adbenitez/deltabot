# -*- coding: utf-8 -*-
from urllib.parse import quote_plus, unquote_plus
import gettext
import os
import re

from simplebot import Plugin
import bs4
import requests
from jinja2 import Environment, PackageLoader, select_autoescape


EQUAL_TOKEN = 'simplebot_e_token'
COLON_TOKEN = 'simplebot_c_token'
E_AMP_TOKEN = 'simplebot_ea_token'
HEADERS = {
    'user-agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0'}
MAX_SIZE_MB = 5
MAX_SIZE = MAX_SIZE_MB*1024**2


class WebGrabber(Plugin):

    name = 'WebGrabber'
    version = '0.3.0'

    @classmethod
    def activate(cls, bot):
        super().activate(bot)
        cls.TEMP_FILE = os.path.join(cls.bot.basedir, cls.name+'.html')
        cls.env = Environment(
            loader=PackageLoader(__name__, 'templates'),
            #autoescape=select_autoescape(['html', 'xml'])
        )
        localedir = os.path.join(os.path.dirname(__file__), 'locale')
        lang = gettext.translation('simplebot_webgrabber', localedir=localedir,
                                   languages=[bot.locale], fallback=True)
        lang.install()
        cls.description = _('Access the web using DeltaChat.')
        cls.commands = [
            ('/ddg', ['<text>'], _('Search in DuckDuckGo'), cls.ddg_cmd),
            ('/wt', ['<text>'], _('Search in Wiktionary'), cls.wt_cmd),
            ('/w', ['<text>'], _('Search in Wikipedia'), cls.w_cmd),
            ('/web', ['<url>'], _('Get a webpage or file'), cls.web_cmd),
            ('/web/app', [], _('Sends an html app to help you to use the plugin.'), cls.app_cmd)]
        cls.bot.add_commands(cls.commands)
        cls.NOSCRIPT = _(
            'You need a browser with JavaScript support for this page to work correctly.')

    @classmethod
    def send_page(cls, chat, url):
        if not url.startswith('http'):
            url = 'http://'+url
        try:
            with requests.get(url, headers=HEADERS, stream=True) as r:
                r.raise_for_status()
                r.encoding = 'utf-8'
                cls.bot.logger.debug(
                    'Content type: {}'.format(r.headers['content-type']))
                if 'text/html' in r.headers['content-type']:
                    soup = bs4.BeautifulSoup(r.text, 'html.parser')
                    [t.extract() for t in soup(
                        ['script', 'iframe', 'noscript', 'link', 'meta'])]
                    soup.body.append(soup.new_tag('meta', charset='utf-8'))
                    [comment.extract() for comment in soup.find_all(
                        text=lambda text: isinstance(text, bs4.Comment))]
                    for t in soup(['img']):
                        src = t.get('src')
                        if src:
                            t.name = 'a'
                            t['href'] = src
                            t.string = '[{}]'.format(t.get('alt', 'IMAGE'))
                            del t['src'], t['alt']
                        else:
                            t.extract()
                    if r.url.startswith('https://www.startpage.com'):
                        for a in soup('a', href=True):
                            url = a['href'].split(
                                'startpage.com/cgi-bin/serveimage?url=')
                            if len(url) == 2:
                                a['href'] = unquote_plus(url[1])
                    for a in soup('a', href=True):
                        if not a['href'].startswith('mailto:'):
                            a['href'] = a['href'].replace('=', EQUAL_TOKEN)
                            a['href'] = a['href'].replace(':', COLON_TOKEN)
                            a['href'] = a['href'].replace('%26', E_AMP_TOKEN)
                    styles = [str(s) for s in soup.find_all('style')]
                    for t in soup(lambda t: t.has_attr('class') or t.has_attr('id')):
                        classes = []
                        for c in t.get('class', []):
                            for s in styles:
                                if '.'+c in s:
                                    classes.append(c)
                                    break
                        del t['class']
                        if classes:
                            t['class'] = ' '.join(classes)
                        if t.get('id') is not None:
                            for s in styles:
                                if '#'+t['id'] in s:
                                    break
                            else:
                                del t['id']
                    script = r'for(let a of document.getElementsByTagName("a"))if(a.href&&-1===a.href.indexOf("mailto:")){const b=encodeURIComponent(`${a.getAttribute("href").replace(/^(?!https?:\/\/|\/\/)\.?\/?(.*)/,`${simplebot_url}/$1`)}`);a.href=`mailto:${"' + WebGrabber.bot.get_address(
                    ) + r'"}?body=/web%20${b}`}'
                    t = soup.new_tag('script')
                    index = r.url.find('/', 8)
                    if index >= 0:
                        url = r.url[:index]
                    else:
                        url = r.url
                    t.string = 'var simplebot_url = "{}";'.format(url)+script
                    soup.body.append(t)
                    with open(cls.TEMP_FILE, 'w') as fd:
                        fd.write(str(soup))
                    chat.send_file(cls.TEMP_FILE, mime_type='text/html')
                else:
                    chunks = r.iter_content(chunk_size=MAX_SIZE)
                    chunk = chunks.__next__()
                    if len(chunk) < MAX_SIZE:
                        d = r.headers.get('content-disposition', None)
                        if d is not None:
                            fname = re.findall(
                                "filename=(.+)", d)[0].strip('"')
                        else:
                            fname = r.url.split('/').pop().split('?')[0]
                            if '.' not in fname:
                                if 'image/png' in r.headers['content-type']:
                                    fname += '.png'
                                elif 'image/jpeg' in r.headers['content-type']:
                                    fname += '.jpg'
                        fpath = os.path.join(
                            cls.bot.basedir, 'account.db-blobs', fname)
                        with open(fpath, 'wb') as fd:
                            fd.write(chunk)
                        chat.send_file(fpath)
                    else:
                        chat.send_text(
                            _('Only files smaller than {}MB are allowed').format(MAX_SIZE_MB))
        except Exception as ex:      # TODO: too much generic
            cls.bot.logger.exception(ex)
            chat.send_text(_('Falied to get url:\n{}').format(url))

    @classmethod
    def app_cmd(cls, msg, arg):
        chat = cls.bot.get_chat(msg)
        template = cls.env.get_template('index.html')
        with open(cls.TEMP_FILE, 'w') as fd:
            fd.write(template.render(
                plugin=cls, bot_addr=cls.bot.get_address()))
        chat.send_file(cls.TEMP_FILE, mime_type='text/html')

    @classmethod
    def web_cmd(cls, msg, url):
        url = url.replace(EQUAL_TOKEN, '=')
        url = url.replace(COLON_TOKEN, ':')
        url = url.replace(E_AMP_TOKEN, '%26')
        cls.send_page(cls.bot.get_chat(msg), url)

    @classmethod
    def ddg_cmd(cls, msg, arg):
        cls.send_page(cls.bot.get_chat(msg),
                      "https://duckduckgo.com/lite?q={}".format(quote_plus(arg)))

    @classmethod
    def w_cmd(cls, msg, arg):
        cls.send_page(cls.bot.get_chat(
            msg), "https://{}.m.wikipedia.org/wiki/?search={}".format(cls.bot.locale, quote_plus(arg)))

    @classmethod
    def wt_cmd(cls, msg, arg):
        cls.send_page(cls.bot.get_chat(
            msg), "https://{}.m.wiktionary.org/wiki/?search={}".format(cls.bot.locale, quote_plus(arg)))
