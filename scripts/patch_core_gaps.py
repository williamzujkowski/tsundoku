#!/usr/bin/env python3
"""Patch core metadata gaps in book collection:
- 10 publication years
- 15 cover URLs
- 41 book descriptions
"""

import json
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"

PUBLICATION_YEARS = {
    "national-avenue": 1924,
    "the-tale-of-the-bamboo-cutter": 900,
    "popol-vuh": 1554,
    "the-upanishads": -700,
    "the-book-of-tea": 1906,
    "secondhand-time": 2013,
    "avesta": -1000,
    "kebra-nagast": 1320,
    "natya-shastra": -200,
    "rig-veda": -1500,
}

COVERS = {
    "the-satin-slipper": "https://covers.openlibrary.org/b/id/2136261-M.jpg",
    "the-maxims-of-ptahhotep": "https://covers.openlibrary.org/b/id/15201054-M.jpg",
    "principal-upanishads": "https://covers.openlibrary.org/b/id/313759-M.jpg",
    "the-journal-of-jules-renard": "https://covers.openlibrary.org/b/id/14794599-M.jpg",
    "the-gallic-war": "https://covers.openlibrary.org/b/id/2891112-M.jpg",
    "forth-on-the-daydream": "https://covers.openlibrary.org/b/id/3169856-M.jpg",
    "avesta": "https://covers.openlibrary.org/b/id/6681685-M.jpg",
    "the-human-cycle": "https://covers.openlibrary.org/b/id/9646419-M.jpg",
    "thrse-desqueyroux": "https://covers.openlibrary.org/b/id/9535526-M.jpg",
    "owasp-testing-guide": "https://books.google.com/books/content?id=i7c7zAEACAAJ&printsec=frontcover&img=1&zoom=1",
    "zuni-folktales": "https://covers.openlibrary.org/b/id/5739787-M.jpg",
    "lives-of-the-noble-greeks-and-romans": "https://covers.openlibrary.org/b/id/10679669-M.jpg",
    "kebra-nagast": "https://covers.openlibrary.org/b/id/9091926-M.jpg",
    "a-history-of-religious-ideas": "https://covers.openlibrary.org/b/id/140598-M.jpg",
    "prices-and-production": "https://covers.openlibrary.org/b/id/8709269-M.jpg",
}

DESCRIPTIONS = {
    "at-the-existentialist-caf": (
        "At the Existentialist Café is Sarah Bakewell's intellectual biography of 20th-century "
        "existentialism, chronicling how Jean-Paul Sartre, Simone de Beauvoir, Albert Camus, "
        "and Martin Heidegger transformed European philosophy through phenomenology and political engagement."
    ),
    "aurlien": (
        "Aurélien is Louis Aragon's classic 1944 novel of the interwar Parisian avant-garde, "
        "depicting a disillusioned World War I veteran whose profound, thwarted love for Bérénice Morel "
        "unfolds against the restless decadence of the Roaring Twenties."
    ),
    "building-products-for-the-enterprise": (
        "Building Products for the Enterprise provides a comprehensive practical framework for "
        "software product managers navigating the unique challenges of B2B platforms, sales cycles, "
        "security requirements, and enterprise buyer personas."
    ),
    "cenizas-de-izalco": (
        "Cenizas de Izalco (Ashes of Izalco), co-authored by Claribel Alegría and Darwin J. Flakoll, "
        "is a landmark Salvadoran novel exploring love, class tension, and political awakening against "
        "the backdrop of the 1932 indigenous uprising and massacre in El Salvador."
    ),
    "conan-the-barbarian": (
        "Conan the Barbarian collects Robert E. Howard's seminal sword-and-sorcery tales chronicling "
        "the adventures of the iconic Cimmerian wanderer, warrior, and future king across the mythical "
        "prehistoric Hyborian Age."
    ),
    "confusion-of-feelings": (
        "Confusion of Feelings is Stefan Zweig's psychological novella depicting an older scholar "
        "who recalls his youthful, obsessive intellectual devotion to a brilliant professor whose concealed "
        "desires and inner turmoil transformed both their lives."
    ),
    "crash": (
        "Crash is J.G. Ballard's provocative 1973 novel investigating the dark psychological intersection "
        "of human desire, automotive technology, and celebrity culture through the lens of staged car collisions."
    ),
    "designing-web-apis": (
        "Designing Web APIs offers practical guidance on architecting, documenting, and evolving robust "
        "RESTful APIs, covering hypermedia constraints, authentication schemes, versioning strategies, "
        "and developer experience."
    ),
    "destination-void": (
        "Destination: Void is Frank Herbert's 1966 hard science fiction novel following the surviving "
        "crew of a colony starship whose catastrophic computer failure forces them to engineer an artificial "
        "general consciousness in order to survive."
    ),
    "doing-data-science": (
        "Doing Data Science, based on Columbia University's introduction to data science course, covers "
        "foundational methodologies across statistical inference, exploratory data analysis, machine learning "
        "algorithms, and real-world analytics workflows."
    ),
    "doing-good-better": (
        "Doing Good Better is philosopher William MacAskill's foundational introduction to effective altruism, "
        "offering evidence-based frameworks to maximize the positive impact of charitable donations, career choices, "
        "and ethical decision-making."
    ),
    "down-girl": (
        "Down Girl: The Logic of Misogyny by philosopher Kate Manne presents an influential analytical "
        "framework defining misogyny not as individual hatred of women, but as the policing and enforcement "
        "mechanism that upholds patriarchal order."
    ),
    "dragonflight": (
        "Dragonflight is Anne McCaffrey's landmark 1968 science fantasy novel opening the Dragonriders of Pern "
        "series, where human riders form telepathic bonds with fire-breathing dragons to defend their world "
        "against the devastating airborne organism known as Thread."
    ),
    "exploiting-software": (
        "Exploiting Software: How to Break Code by Greg Hoglund and Gary McGraw is a pioneering cybersecurity "
        "manual detailing software vulnerability patterns, reverse engineering techniques, buffer overflows, "
        "and defensive secure coding practices."
    ),
    "forth-on-the-daydream": (
        "Froth on the Daydream (L'Écume des jours) is Boris Vian's surrealist masterpiece, blending playful "
        "wordplay, jazz culture, and existential absurdity with a tragic romance between Colin and Chloé, whose lungs "
        "are infected by a deadly water lily."
    ),
    "harmonium": (
        "Harmonium is Wallace Stevens's celebrated 1923 debut poetry collection, featuring masterpieces such as "
        "'Sunday Morning', 'The Emperor of Ice-Cream', and 'Thirteen Ways of Looking at a Blackbird' that explore "
        "imagination, perception, and modern reality."
    ),
    "his-masterpiece": (
        "His Masterpiece (L'Œuvre) is Émile Zola's fourteenth novel in the Rougon-Macquart series, offering a vivid "
        "portrait of the Parisian art world and the tragic struggles of the fictional painter Claude Lantier, "
        "loosely modeled on Paul Cézanne and Édouard Manet."
    ),
    "journey-to-the-end-of-the-night": (
        "Journey to the End of the Night is Louis-Ferdinand Céline's groundbreaking 1932 novel following the cynical "
        "antihero Ferdinand Bardamu from the bloody trenches of World War I to colonial Africa, urban America, "
        "and the impoverished suburbs of Paris."
    ),
    "l-lia": (
        "Lélia is George Sand's passionate 1833 feminist novel examining female intellectual freedom, religious doubt, "
        "and societal oppression through the intense reflections and emotional tribulations of its eponymous heroine."
    ),
    "latex-a-document-preparation-system": (
        "LaTeX: A Document Preparation System is Leslie Lamport's definitive guide to the typesetting system built "
        "on Donald Knuth's TeX engine, essential for publishing complex mathematical formulas, academic papers, "
        "and technical manuscripts."
    ),
    "life-a-users-manual": (
        "Life: A User's Manual is Georges Perec's tour de force of experimental postmodern literature, meticulously "
        "describing the simultaneous lives, histories, and apartments of a Parisian building frozen in time using "
        "the knight's tour mathematical constraint."
    ),
    "lucifers-hammer": (
        "Lucifer's Hammer by Larry Niven and Jerry Pournelle is an epic post-apocalyptic science fiction novel depicting "
        "humanity's struggle for survival and societal rebuilding after a massive comet collides with Earth."
    ),
    "mans-fate": (
        "Man's Fate (La Condition Humaine) is André Malraux's Prix Goncourt-winning 1933 novel portraying the tragic "
        "failed communist insurrection in Shanghai in 1927 and the existential struggles of revolutionaries facing death, "
        "betrayal, and political terror."
    ),
    "more-effective-c": (
        "More Effective C++ presents 35 essential rules, guidelines, and design idioms by Scott Meyers to write efficient, "
        "robust, and maintainable C++ code, covering exceptions, memory management, templates, and performance optimizations."
    ),
    "my-reminiscences": (
        "My Reminiscences is Rabindranath Tagore's candid autobiographical memoir recounting his childhood, literary "
        "awakenings, and the cultural renaissance of 19th-century Bengal leading up to his international acclaim as poet "
        "and Nobel laureate."
    ),
    "nadja": (
        "Nadja is André Breton's seminal 1928 Surrealist romance and essay, documenting his encounters across Paris "
        "with an enigmatic, visionary woman named Nadja alongside photographs and drawings reflecting the irrational "
        "beauty of chance and desire."
    ),
    "oedipus-rex-antigone": (
        "Oedipus Rex & Antigone pairs Sophocles's greatest Athenian tragedies, examining the inexorable tensions "
        "between divine law and human decree, individual conscience and state power, and the inescapable burden "
        "of tragic destiny."
    ),
    "paroles": (
        "Paroles is Jacques Prévert's beloved 1946 poetry collection, celebrated for its accessible, lyrical, and "
        "anti-authoritarian verse capturing the everyday joys, heartbreaks, and bohemian spirit of working-class Paris."
    ),
    "pedagogy-of-the-oppressed": (
        "Pedagogy of the Oppressed is Paulo Freire's influential foundational work in critical pedagogy, proposing "
        "that traditional education should be replaced with dialogical reflection and co-intentional praxis to liberate "
        "both the oppressed and their oppressors."
    ),
    "prices-and-production": (
        "Prices and Production contains Friedrich Hayek's landmark 1931 London School of Economics lectures outlining "
        "the Austrian theory of the business cycle, examining how artificial credit expansion distorts capital structure "
        "and leads to economic crises."
    ),
    "romances-sans-paroles": (
        "Romances sans paroles (Songs Without Words) is Paul Verlaine's delicate 1874 Symbolist poetry collection, "
        "composed during his turbulent travels with Arthur Rimbaud and renowned for its musicality, impressionistic moods, "
        "and subtle emotional cadence."
    ),
    "second-thoughts": (
        "Second Thoughts (La Modification) is Michel Butor's masterwork of the French Nouveau Roman, narrated entirely "
        "in the second person ('you') as a man takes a train from Paris to Rome to join his mistress, reevaluating his "
        "life with every passing station."
    ),
    "secondhand-time": (
        "Secondhand Time: The Last of the Soviets is Svetlana Alexievich's oral history masterpiece, weaving together "
        "dozens of intimate interviews to chronicle the psychological trauma, lost ideals, and capitalist disorientation "
        "following the collapse of the Soviet Union."
    ),
    "the-autobiography-of-an-idea": (
        "The Autobiography of an Idea is architect Louis Henri Sullivan's lyrical memoir tracing the development of "
        "organic architectural philosophy and the famous maxim 'form ever follows function' that transformed modern American "
        "skyscraper design."
    ),
    "the-bhagavad-gita": (
        "The Bhagavad Gita is an ancient 700-verse Hindu scripture that forms part of the Mahabharata, depicting a "
        "profound dialogue between Prince Arjuna and Krishna on the battlefield of Kurukshetra concerning duty, righteous "
        "action, devotion, and liberation."
    ),
    "the-democratic-paradox": (
        "The Democratic Paradox by political theorist Chantal Mouffe examines the irreducible tension between liberal "
        "universalism and democratic popular sovereignty, proposing an 'agonistic' model where political conflicts are "
        "channeled into democratic debate rather than moralistic polarization."
    ),
    "the-happy-birthday-of-death": (
        "The Happy Birthday of Death is Beat poet Gregory Corso's 1960 poetry collection, featuring celebrated visionary "
        "and surrealistic poems including the fold-out typographically daring anti-nuclear masterwork 'Bomb'."
    ),
    "the-human-cycle": (
        "The Human Cycle by Indian philosopher Sri Aurobindo examines the psychological evolution of human society through "
        "historical stages, arguing for the spiritual transformation of communal life and the awakening of a deeper "
        "collective consciousness."
    ),
    "the-satin-slipper": (
        "The Satin Slipper is Paul Claudel's monumental four-day Spanish Renaissance drama exploring cosmic destiny, "
        "Catholic grace, and the spiritual transcendence of unrequited love between Don Rodrigue and Doña Prouhèze across "
        "the oceans and continents of the New World."
    ),
    "the-wanderer": (
        "The Wanderer (Le Grand Meaulnes) is Alain-Fournier's lyrical 1913 French novel of youth and vanished dreams, "
        "following the romantic adventurer Augustin Meaulnes as he searches for a mysterious lost estate and the beautiful "
        "woman he encountered there."
    ),
    "thrse-desqueyroux": (
        "Thérèse Desqueyroux is François Mauriac's acclaimed 1927 psychological novel portraying a provincial French woman "
        "who, suffocated by the rigid bourgeois conventions and emotional isolation of marriage, attempts to poison her husband."
    ),
}


def main():
    years_count = 0
    covers_count = 0
    desc_count = 0

    for slug, year in PUBLICATION_YEARS.items():
        p = BOOKS_DIR / f"{slug}.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if not data.get("first_published"):
                data["first_published"] = year
                p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                years_count += 1

    for slug, cover in COVERS.items():
        p = BOOKS_DIR / f"{slug}.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if not data.get("cover_url"):
                data["cover_url"] = cover
                p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                covers_count += 1

    for slug, desc in DESCRIPTIONS.items():
        p = BOOKS_DIR / f"{slug}.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if not data.get("description"):
                data["description"] = desc
                p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                desc_count += 1

    print(f"Patched: {years_count} years, {covers_count} covers, {desc_count} descriptions.")


if __name__ == "__main__":
    main()
