#!/usr/bin/env python3
"""
EPG XML merger and deduplicator.
XMLTV format: root <tv>, children <channel id="..."> and <programme channel="..." start="..." stop="...">.
Dedup keys: channel → id attr; programme → (channel, start, stop) tuple.
Outputs one XML file per country group into output_dir defined in sources.yml.
"""

import sys
import yaml
import requests
import gzip
import io
from lxml import etree
from pathlib import Path

SOURCES_FILE = Path("sources.yml")
TIMEOUT      = 30  # seconds per request


def fetch_xml(url: str) -> bytes:
    """Download XML or gzipped XML, return raw bytes."""
    r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "EPG-Merger/1.0"})
    r.raise_for_status()
    content = r.content
    # Auto-detect gzip by magic bytes
    if content[:2] == b"\x1f\x8b":
        with gzip.open(io.BytesIO(content)) as f:
            content = f.read()
    return content


def parse_tree(raw: bytes) -> etree._Element:
    parser = etree.XMLParser(remove_blank_text=True, recover=True)
    return etree.fromstring(raw, parser)


def merge_sources(urls: list[str]) -> etree._Element:
    """
    Returns a merged <tv> root element.
    Deduplication:
      - <channel>: keyed on 'id' attribute
      - <programme>: keyed on (channel, start, stop) tuple
    """
    root = etree.Element("tv")
    seen_channels:   set[str]             = set()
    seen_programmes: set[tuple[str, ...]] = set()
    failed = 0

    for url in urls:
        print(f"  Fetching: {url}")
        try:
            raw  = fetch_xml(url)
            tree = parse_tree(raw)
        except Exception as e:
            print(f"  WARN: failed ({e})", file=sys.stderr)
            failed += 1
            continue

        for elem in tree:
            tag = elem.tag

            if tag == "channel":
                cid = elem.get("id", "")
                if cid and cid not in seen_channels:
                    seen_channels.add(cid)
                    root.append(elem)

            elif tag == "programme":
                key = (
                    elem.get("channel", ""),
                    elem.get("start",   ""),
                    elem.get("stop",    ""),
                )
                if all(key) and key not in seen_programmes:
                    seen_programmes.add(key)
                    root.append(elem)

    print(f"\nResult: {len(seen_channels)} channels, "
          f"{len(seen_programmes)} programmes, {failed} source(s) failed")
    return root


def main():
    cfg        = yaml.safe_load(SOURCES_FILE.read_text())
    output_dir = Path(cfg.get("output_dir", "output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    for country, group in cfg["sources"].items():
        urls   = group["urls"]
        output = output_dir / group["output"]

        print(f"\n{'='*50}")
        print(f"Country : {country.upper()}")
        print(f"Sources : {len(urls)}")
        print(f"Output  : {output}")
        print('='*50)

        root = merge_sources(urls)

        tree = etree.ElementTree(root)
        tree.write(str(output), pretty_print=True, xml_declaration=True, encoding="UTF-8")
        print(f"Written : {output}")


if __name__ == "__main__":
    main()
