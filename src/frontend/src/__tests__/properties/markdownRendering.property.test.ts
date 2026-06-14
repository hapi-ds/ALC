import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { renderMarkdown } from "../../lib/renderMarkdown";

// ---------------------------------------------------------------------------
// Arbitrary generators for markdown content
// ---------------------------------------------------------------------------

/**
 * Generator for a header level between 1 and 6.
 */
const arbHeaderLevel = fc.integer({ min: 1, max: 6 });

/**
 * Generator for header text that is non-empty and doesn't contain
 * characters that would interfere with the markdown heading regex.
 * We use alphanumeric + spaces to keep tests focused on the structural property.
 */
const arbHeaderText = fc
  .array(fc.constantFrom(...("abcdefghijklmnopqrstuvwxyz0123456789 ".split(""))), {
    minLength: 1,
    maxLength: 40,
  })
  .map((chars) => chars.join(""))
  .filter((text) => text.trim().length > 0);

/**
 * Generator for link text (non-empty, simple alphanumeric).
 */
const arbLinkText = fc
  .array(fc.constantFrom(...("abcdefghijklmnopqrstuvwxyz0123456789 ".split(""))), {
    minLength: 1,
    maxLength: 30,
  })
  .map((chars) => chars.join(""))
  .filter((text) => text.trim().length > 0);

/**
 * Generator for a URL (simple http/https URLs).
 */
const arbUrl = fc
  .tuple(
    fc.constantFrom("http", "https"),
    fc.array(fc.constantFrom(...("abcdefghijklmnopqrstuvwxyz0123456789".split(""))), {
      minLength: 3,
      maxLength: 15,
    }),
    fc.constantFrom(".com", ".org", ".io", ".net"),
    fc.constantFrom("", "/path", "/page", "/docs/intro")
  )
  .map(([protocol, domainChars, tld, path]) => `${protocol}://${domainChars.join("")}${tld}${path}`);

// ---------------------------------------------------------------------------
// Property 6: Markdown Rendering Produces Valid HTML Structure
// Validates: Requirements 3.3
// ---------------------------------------------------------------------------

describe("Feature: document-content-viewer, Property 6: Markdown Rendering Produces Valid HTML Structure", () => {
  /**
   * **Validates: Requirements 3.3**
   *
   * For any markdown string containing a header (# through ######),
   * the rendered HTML contains the corresponding <h1> through <h6> element.
   */
  it("markdown headers produce corresponding HTML heading elements", () => {
    fc.assert(
      fc.property(arbHeaderLevel, arbHeaderText, (level, text) => {
        const hashes = "#".repeat(level);
        const markdown = `${hashes} ${text}`;
        const html = renderMarkdown(markdown);

        const expectedTag = `<h${level}`;
        expect(html).toContain(expectedTag);
      }),
      { numRuns: 200 }
    );
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * For any markdown string containing a header, the rendered HTML
   * contains the header text within the heading element.
   */
  it("rendered heading contains the original header text", () => {
    fc.assert(
      fc.property(arbHeaderLevel, arbHeaderText, (level, text) => {
        const hashes = "#".repeat(level);
        const markdown = `${hashes} ${text}`;
        const html = renderMarkdown(markdown);

        // The regex `^#\s+(.+)$` captures everything after the whitespace separator,
        // but .+ will capture the trimmed content. Leading spaces in text become part
        // of the \s+ match, so we check for the trimmed text content.
        const expectedText = text.replace(/^\s+/, "");
        if (expectedText.length > 0) {
          expect(html).toContain(expectedText);
        }
      }),
      { numRuns: 200 }
    );
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * The heading tag level in the output matches the number of # characters
   * in the input (e.g., ## → h2, #### → h4).
   */
  it("heading tag level matches the number of # characters", () => {
    fc.assert(
      fc.property(arbHeaderLevel, arbHeaderText, (level, text) => {
        const hashes = "#".repeat(level);
        const markdown = `${hashes} ${text}`;
        const html = renderMarkdown(markdown);

        // Should contain the correct level tag
        const expectedOpenTag = `<h${level}`;
        const expectedCloseTag = `</h${level}>`;
        expect(html).toContain(expectedOpenTag);
        expect(html).toContain(expectedCloseTag);

        // Should NOT contain other heading levels for this specific input
        for (let otherLevel = 1; otherLevel <= 6; otherLevel++) {
          if (otherLevel !== level) {
            expect(html).not.toContain(`<h${otherLevel}`);
          }
        }
      }),
      { numRuns: 200 }
    );
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * Multiple headers in a single markdown string each produce their
   * corresponding heading elements.
   */
  it("multiple headers each produce their corresponding heading elements", () => {
    fc.assert(
      fc.property(
        fc.array(fc.tuple(arbHeaderLevel, arbHeaderText), {
          minLength: 2,
          maxLength: 6,
        }),
        (headers) => {
          const markdown = headers
            .map(([level, text]) => `${"#".repeat(level)} ${text}`)
            .join("\n\n");
          const html = renderMarkdown(markdown);

          for (const [level] of headers) {
            expect(html).toContain(`<h${level}`);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * For any markdown string containing a link [text](url),
   * the rendered HTML contains an <a> element with the correct href.
   */
  it("markdown links produce corresponding <a> elements with href", () => {
    fc.assert(
      fc.property(arbLinkText, arbUrl, (text, url) => {
        const markdown = `[${text}](${url})`;
        const html = renderMarkdown(markdown);

        expect(html).toContain("<a");
        expect(html).toContain(`href=`);
        expect(html).toContain(url);
      }),
      { numRuns: 200 }
    );
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * For any markdown string containing a link [text](url),
   * the rendered HTML contains the link text within the <a> element.
   */
  it("rendered link contains the original link text", () => {
    fc.assert(
      fc.property(arbLinkText, arbUrl, (text, url) => {
        const markdown = `[${text}](${url})`;
        const html = renderMarkdown(markdown);

        expect(html).toContain(text);
        expect(html).toContain("<a");
      }),
      { numRuns: 200 }
    );
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * renderMarkdown always returns a non-empty string for non-empty input.
   */
  it("renderMarkdown always returns a non-empty string for non-empty input", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        (markdown) => {
          const html = renderMarkdown(markdown);
          expect(html.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});
