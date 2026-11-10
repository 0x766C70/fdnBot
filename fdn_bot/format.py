"""Nettoyage brut des réponses à destinations sans rendu markdown.

Le front (HTML statique servi par Vercel) et la CLI affichent la réponse
telle quelle : le prompt demande du texte brut, mais les LLM glissent
souvent du markdown quand même. `strip_markdown` retire ce marquage pour
qu'aucune astérisque ni dièse ne s'affiche littéralement.
"""

from __future__ import annotations

import re

_PLACEHOLDER = "\x00{}\x00"

_CODE_BLOCK = re.compile(
    r"^[ \t]*(```|~~~)[^\n]*\n(.*?)^[ \t]*\1[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_HR = re.compile(
    r"^[ \t]*(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$",
    re.MULTILINE,
)
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
_ITALIC_STAR = re.compile(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])")
_ITALIC_US = re.compile(r"(?<!\w)_(?![_\s])(.+?)(?<![_\s])_(?!\w)")
_HEADER = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_HEADER_TRAILING = re.compile(r"[ \t]#+[ \t]*$", re.MULTILINE)
_QUOTE = re.compile(r"^[ \t]*(?:>[ \t]?)+", re.MULTILINE)
_TABLE_SEP = re.compile(r"^[ \t]*\|[ \t:|-]+\|[ \t]*$\n?", re.MULTILINE)
_TABLE_ROW = re.compile(r"^[ \t]*\|(.+)\|[ \t]*$", re.MULTILINE)
_BULLET_STAR = re.compile(r"^([ \t]*)\*[ \t]+", re.MULTILINE)
_BULLET_PLUS = re.compile(r"^([ \t]*)\+[ \t]+", re.MULTILINE)
_BLANKS = re.compile(r"\n{3,}")


def strip_markdown(text: str) -> str:
    """Retourne `text` sans les marqueurs markdown usuels.

    Le contenu est préservé (gras/italique perdent leurs astérisques,
    les liens gardent texte et URL, les blocs de code gardent leur
    contenu et perdent leurs clôtures).
    """
    stash: list[str] = []

    def _keep(match: re.Match) -> str:
        stash.append(match.group(0))
        return _PLACEHOLDER.format(len(stash) - 1)

    def _keep_block(match: re.Match) -> str:
        # seul le contenu du bloc est conservé, sans les lignes de clôture
        stash.append(match.group(2).rstrip("\n"))
        return _PLACEHOLDER.format(len(stash) - 1)

    text = text.replace("\r\n", "\n")
    text = _CODE_BLOCK.sub(_keep_block, text)
    text = _INLINE_CODE.sub(lambda m: _keep_inner(m, stash), text)
    text = _HR.sub("", text)
    text = _IMAGE.sub(r"\2", text)
    text = _LINK.sub(r"\1 (\2)", text)
    text = _BOLD.sub(r"\1", text)
    text = _ITALIC_STAR.sub(r"\1", text)
    text = _ITALIC_US.sub(r"\1", text)
    text = text.replace("**", "")
    text = _HEADER.sub("", text)
    text = _HEADER_TRAILING.sub("", text)
    text = _QUOTE.sub("", text)
    text = _TABLE_SEP.sub("", text)
    text = _TABLE_ROW.sub(
        lambda m: "   ".join(part.strip() for part in m.group(1).split("|")), text
    )
    text = _BULLET_STAR.sub(r"\1- ", text)
    text = _BULLET_PLUS.sub(r"\1- ", text)
    for index, chunk in enumerate(stash):
        text = text.replace(_PLACEHOLDER.format(index), chunk)
    text = _BLANKS.sub("\n\n", text)
    return text.strip()


def _keep_inner(match: re.Match, stash: list[str]) -> str:
    # le code inline garde son contenu mais perd ses backticks
    stash.append(match.group(1))
    return _PLACEHOLDER.format(len(stash) - 1)
