// remarque-tokens/deck ships plain ESM without a type declaration.
declare module 'remarque-tokens/deck' {
  export interface Deck {
    names: string[];
    current(): string | null;
    apply(name: string | null, opts?: { persist?: boolean }): void;
    restore(): string | null;
  }
  export function createDeck(
    palettes: (string | { name: string })[],
    opts?: { root?: HTMLElement; storageKey?: string },
  ): Deck;
  export function bindPicker(
    deck: Deck,
    container: ParentNode,
    opts?: { onChange?: (name: string | null) => void },
  ): { sync(): void };
}
