#!/usr/bin/env python3
# encoding: utf-8

"""
A "Proof-Of-Concept" project which aims to aid SVG Comic strips translations.
"""

__version__ = "0.1"

import re
import os
import json
import nltk
import codecs
import logging
import argparse

from lxml import etree
from textwrap import wrap
from urllib import request
from urllib.parse import quote

TEXT_TAG = re.compile("^\{.*?\}text$")
TSPAN_TAG = re.compile("^\{.*?\}tspan$")
INVALID_TEXT = re.compile("[<>^*=]")

URL = "http://translate.google.com/translate_a/" +\
    "t?client=p&ie=UTF-8&oe=UTF-8&sl={from_lang}&tl={to_lang}&text={text}"

AUTODETECT_URL = "http://translate.google.com/translate_a/" +\
    "t?client=p&ie=UTF-8&oe=UTF-8&tl={to_lang}&text={text}"

log = None


def translate(text, from_lang, to_lang):
    text = quote(text, '')
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux i586; ' +
                      'rv:31.0) Gecko/20100101 Firefox/31.0'
        }
    if from_lang:
        url = URL.format(
            text=text,
            from_lang=from_lang,
            to_lang=to_lang,
            )
    else:
        url = AUTODETECT_URL.format(
            text=text,
            to_lang=to_lang,
            )
    req = request.Request(url=url, headers=headers)
    r = request.urlopen(req)
    out = json.loads(r.read().decode('utf-8'))
    log.info("After translation: {}".format(out['sentences'][0]['trans']))
    return out['sentences'][0]['trans']


def translate_split_paragraph(paragraph, from_lang, to_lang):
    size = len(paragraph)
    max_size = max([len(text) for (child, text) in paragraph])

    raw_paragraph = ' '.join([text.strip() for (child, text) in paragraph])
    if raw_paragraph.lower() == 'creative commons':
        return

    log.info("Paragraph: {}".format(raw_paragraph))

    log.debug("Tokenizing phrases.")
    phrases = nltk.sent_tokenize(raw_paragraph)
    phrases = ' '.join([translate(phrase, from_lang, to_lang) for phrase in phrases])
    log.debug("Wrapping paragraph to {}".format(max_size - 1))
    translated_paragraph = wrap(phrases, max_size - 1, replace_whitespace=True)

    new_size = len(translated_paragraph)
    if new_size > size:
        log.debug(
            "Translated text bigger then original. Joining last two lines."
            )
        diff = new_size - size
        tail = ' '.join([translated_paragraph.pop(-1) for i in range(diff)])
        translated_paragraph[-1] = ' '.join([translated_paragraph[-1], tail])

    if new_size < size:
        log.debug(
            "Translated text smaller then original. Padding exceeding lines."
            )
        diff = size - new_size
        for i in range(diff):
            translated_paragraph.append('')

    for ((child, text), translated_text) in \
            zip(paragraph, translated_paragraph):
        child.text = translated_text
        log.debug("Text replaced!")


def get_text_tags(fname):
    log.debug("Reading and parsing file...")
    with codecs.open(fname, 'r', 'utf-8') as fd:
        tree = etree.parse(fd)

    return (tree, [elem for elem in tree.iter() if TEXT_TAG.match(elem.tag)])


def get_out_name(fname, out_pattern):
    path = os.path.dirname(fname)
    (fname, extension) = os.path.splitext(os.path.basename(fname))
    log.debug("Path={}, name={}, extension={}".format(path, fname, extension))
    out_name = out_pattern.format(filename=fname, extension=extension)
    out_name = os.path.join(path, out_name)
    log.info("Out filename: {}".format(out_name))
    return out_name


def translate_file(fname, from_lang, to_lang, out_pattern="{filename}_translated{extension}"):
    log.debug("Preparing to translate file '{}'...".format(fname))
    tree, text_list = get_text_tags(fname)
    log.debug("File parsed!")
    for text in text_list:
        if text.text:
            if not INVALID_TEXT.match(text.text):
                log.debug("Text tag with contents: {}".format(text.text))
                translated = translate(text.text, from_lang, to_lang)
                text.text = translated
                log.debug("Text replaced!")
            else:
                log.info("Ignoring invalid text found: {}".format(text.text))

        log.debug("Inspecting children")
        children = text.getchildren()
        paragraph = []
        for child in children:
            log.debug("Inspecting child {}".format(str(child)))
            if TSPAN_TAG.match(child.tag):
                if child.text:
                    if INVALID_TEXT.findall(child.text):
                        log.info(
                            "Ignoring invalid text found: {}".format(child.text)
                            )
                        continue
                    log.debug("Appending child text...")
                    paragraph.append((child, child.text))
                else:
                    log.info(
                        "TSPAN tag is empty: {}".format(child.tag)
                        )
            else:
                log.info(
                    "Tag doesn't match TSPAN. Ignoring: {}".format(child.tag)
                    )

        if paragraph and len(paragraph) == 1:
            (child, text) = paragraph[0]
            log.debug("Single paragraph found: {}".format(text))
            child.text = translate(text, from_lang, to_lang)
            log.debug("Text replaced!")

        if paragraph and len(paragraph) > 1:
            log.debug(
                "Found a paragraph composed by {} parts".format(len(paragraph))
                )
            translate_split_paragraph(paragraph, from_lang, to_lang)

    log.debug("Generating string.")
    out = etree.tostring(tree, encoding='utf-8')
    out_name = get_out_name(fname, out_pattern)
    log.debug("Writing output.")
    with codecs.open(out_name, 'w', 'utf-8') as fd:
        fd.write(out.decode('utf-8'))
    log.debug("Done!")


def validate_file(fname):
    if not os.path.exists(fname):
        log.warning("File '{}' doesn't exist!".format(fname))
        return False

    if not fname.endswith('svg'):
        log.warning("Sorry, the file '{}' isn't an svg file.".format(fname))
        return False

    if os.path.isfile(fname):
        log.debug("File '{}' is valid".format(fname))
        return True


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'files', nargs="+",
        help="SVG Files to translate.",
        )
    parser.add_argument(
        '-f', '--from-lang', action="store", default=None,
        help="Original language from the SVG file.",
        )
    parser.add_argument(
        '-t', '--to-lang', action="store", default="en",
        help="Language for the output SVG file.",
        )
    parser.add_argument(
        '-o', '--out', action="store",
        help="Output pattern. Ex: {filename}_translated{extension}",
        default="{filename}_translated{extension}"
        )
    parser.add_argument(
        '-V', '--verbose', action="store_true", default=False,
        help="Display verbose output.",
        )
    parser.add_argument(
        '-VV', '--more-verbose', action="store_true", default=False,
        help="Display more verbose output.",
        )
    parser.add_argument(
        '-d', '--debug', action="store_true", default=False,
        help="Display debug information.",
        )
    parser.add_argument(
        '-v', '--version', action='version', version='%(prog)s ' + __version__,
        help="Display program version.",
        )
    return parser.parse_args()


def setup_logging(level=logging.WARNING, debug=False):
    global log
    log = logging.getLogger()
    handler = logging.StreamHandler()
    if debug:
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s: %(message)s"
            )
    else:
        formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(level)
    log.setLevel(level)
    log.addHandler(handler)
    return log


if __name__ == '__main__':
    args = parse_args()
    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    elif args.more_verbose:
        level = logging.DEBUG
    else:
        level = logging.WARNING

    setup_logging(level, args.debug)
    log.debug('Arguments: {}'.format(args))

    log.debug("Validating file list: {}".format(str(args.files)))
    fnames = [fname for fname in args.files if validate_file(fname)]

    log.debug("Sorting file list...")
    fnames.sort()
    log.debug("Done: {}".format(str(fnames)))

    for fname in fnames:
        translate_file(fname, args.from_lang, args.to_lang, args.out)
    log.debug("Quitting!")
