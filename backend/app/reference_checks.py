"""Small reviewed references for misconceptions observed during evaluation.

This is not general fact checking: no browsing, API call or source rewrite.
References supplement interpretation and must not be attributed to the teacher.
"""
import re


def reference_checks(source):
    checks = []
    if re.search(r"\bgpl(?:v?[23])?\b", source, re.I):
        checks.append({"topic": "GPL y venta de copias",
            "fact": "La GPL permite vender copias. No impone como regla general limitar el precio a los costes de distribución; existen condiciones particulares sobre ofertas de código fuente. No confundas software libre con software gratuito ni ausencia de copyright.",
            "url": "https://www.gnu.org/licenses/gpl-faq.en.html#DoesTheGPLAllowMoney"})
    if re.search(r"\b(?:bsd|mit|expat)\b", source, re.I) and re.search(r"\b(?:fsf|free software foundation)\b", source, re.I):
        checks.append({"topic": "FSF y licencias permisivas",
            "fact": "La FSF reconoce BSD modificada y Expat/MIT como licencias libres no copyleft compatibles con GPL. Preferir copyleft no significa rechazar todas las licencias permisivas como no libres; distingue las variantes de BSD.",
            "url": "https://www.gnu.org/licenses/license-list.en.html#ModifiedBSD"})
    if re.search(r"\b(?:python|cpython)\b", source, re.I) and re.search(r"compil|interpret|bytecode", source, re.I):
        checks.append({"topic": "Compilación en CPython",
            "fact": "CPython compila el código fuente a bytecode y lo ejecuta en su máquina virtual; decir que Python nunca se compila es una simplificación incorrecta. Distingue compilación a bytecode de compilación a código máquina y no generalices a todas las implementaciones.",
            "url": "https://docs.python.org/3/glossary.html#term-bytecode"})
    return checks
