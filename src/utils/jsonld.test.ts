import { describe, it, expect } from "vitest";
import { safeJsonLd } from "./jsonld";

describe("safeJsonLd", () => {
  it("produces JSON that round-trips back to the original value", () => {
    const obj = { name: "Dune", year: 1965, tags: ["sf", "classic"] };
    expect(JSON.parse(safeJsonLd(obj))).toEqual(obj);
  });

  it("escapes a </script> breakout attempt", () => {
    const payload = { description: "</script><img src=x onerror=alert(1)>" };
    const out = safeJsonLd(payload);
    expect(out).not.toContain("</script>");
    expect(out).not.toContain("<");
    expect(out).not.toContain(">");
    // ...but the data is preserved once parsed
    expect(JSON.parse(out).description).toBe(
      "</script><img src=x onerror=alert(1)>",
    );
  });

  it("escapes ampersands and U+2028/U+2029 line separators", () => {
    const ls = " ";
    const ps = " ";
    const bio = `A & B${ls}C${ps}D`;
    const out = safeJsonLd({ bio });
    expect(out).not.toContain("&");
    expect(out).not.toContain(ls);
    expect(out).not.toContain(ps);
    expect(JSON.parse(out).bio).toBe(bio);
  });
});
