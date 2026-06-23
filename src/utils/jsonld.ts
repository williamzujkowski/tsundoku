/**
 * Serialize a value to JSON for safe embedding inside an inline
 * `<script type="application/ld+json">` block.
 *
 * `JSON.stringify` does not escape `<`, `>`, `&`, or the U+2028/U+2029 line
 * separators. Emitted raw via Astro's `set:html`, a value containing the
 * literal `</script>` (e.g. a poisoned upstream description/bio) would close
 * the script element early and let following markup execute — stored XSS.
 *
 * Escaping `<` and `>` as `<` / `>` keeps the JSON byte-for-byte
 * equivalent (parsers decode the escapes) while making a `</script>` breakout
 * impossible. We also escape `&` and the JS line terminators for robustness.
 */
const UNSAFE_JSONLD = new RegExp("[<>&\\u2028\\u2029]", "g");

export function safeJsonLd(value: unknown): string {
  return JSON.stringify(value).replace(
    UNSAFE_JSONLD,
    (ch) => "\\u" + ch.charCodeAt(0).toString(16).padStart(4, "0"),
  );
}
