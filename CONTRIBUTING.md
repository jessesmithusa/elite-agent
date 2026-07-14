# Contributing to elite-agent

Thank you for contributing! This guide covers two main paths: adding coaching cards and building custom brains.

## Path 1: Coaching Cards

### Add a Card

1. **Copy the template:**
   ```bash
   cp elite_agent/brains/olympic/cards/TEMPLATE.md elite_agent/brains/olympic/cards/my-card.md
   ```

2. **Fill the frontmatter block** (the YAML between `---` lines):
   ```yaml
   ---
   athlete: "Public Figure Name"
   sport: "basketball"
   skill: "staying composed after a setback"
   situation_type: "conflict"
   provenance: "Public source (e.g., memoir, published interview)"
   consent: "public_figure"
   ---
   ```

   Required fields:
   - `athlete` – Public figure name (with public sources cited)
   - `sport` – Sport or activity
   - `skill` – The specific behavior or pattern this story teaches
   - `situation_type` – Must be **exactly one** of:
     - `avoidance` – putting things off, procrastination
     - `overwhelm` – too much at once, information overload
     - `decisiveness` – needing to choose or act fast
     - `conflict` – disagreement with a ref, teammate, opponent, or coach
     - `general` – doesn't fit the others
   - `provenance` – Your source (e.g., "Jane Smith, 'Memoirs of a Champion' (2020)")
   - `consent` – How this athlete's story can be used (e.g., `public_figure`, `public_record`)

3. **Write the card content** (plain Markdown below the frontmatter):
   - Follow the template structure (Moment, What Usually Happens, Premise, Desired Outcome, Controllable Behavior, Review Question, Athlete Level, Notes For Younger Athletes, etc.)
   - Keep language clear and actionable
   - No jargon; write for high-school and college athletes

### Privacy Rules

- **No private data:** Do not include names, emails, phone numbers, medical details, payment details, or recruiting information of private individuals.
- **Public figures only:** Use publicly known athletes or figures with publicly available sources.
- **Cite sources:** Always include a link or citation (e.g., published book, news article, official statement).
- **No private athlete data:** Even if you coached an athlete, do not use their private details, struggles, or personal history without explicit consent.

### Test Your Card

```bash
# Run card structure tests (checks frontmatter, situation_type, athlete field)
python3 -m pytest tests/test_cards.py -v

# Run the personal-data test (ensures no banned strings)
python3 -m pytest tests/test_no_personal_data.py -v
```

Your PR must pass both test suites.

### Submit a PR

1. **Fork** the repo (or create a branch if you have access)
2. **Commit your card(s):**
   ```bash
   git add elite_agent/brains/olympic/cards/my-card.md
   git commit -m "Add coaching card: my-card (situation_type: conflict)"
   ```
3. **Push** and **open a PR** with:
   - Title: `Add card: <athlete-name>-<topic>`
   - Description: brief summary of the card's situation_type and coaching angle
   - Confirm you've run tests and they pass
   - Reference any sources in the PR description if not in the card

## Path 2: Custom Brains

### Design a Brain

A **brain** implements:
- `classify(text: str) -> list[str]` – extract coaching buckets from email text
- `retrieve(buckets: list[str], max_cards: int) -> list[Card]` – fetch cards for those buckets
- `route(subject: str, body: str, risk_flags: bool) -> RouteResult` – combine the above and determine response mode

See `elite_agent/brains/base.py` for the `BaseBrain` interface and `elite_agent/brains/olympic/__init__.py` for a full example.

### Create a Brain Module

1. **Create a package** under `elite_agent/brains/` with a `get_brain(cfg) -> BaseBrain` factory function:
   ```
   elite_agent/brains/
     olympic/          # existing example
     my_brain/
       __init__.py     # implements get_brain(cfg)
       classify.py     # your classification logic
       retrieve.py     # your card retrieval
   ```

2. **Implement the interface:**
   ```python
   from elite_agent.brains.base import BaseBrain, Card, RouteResult
   
   class MyBrain(BaseBrain):
       name = "my_brain"
       
       def classify(self, text: str) -> list[str]:
           # Keyword, ML, or heuristic-based classification
           return ["bucket1", "bucket2"]
       
       def retrieve(self, buckets: list[str], max_cards: int = 3) -> list[Card]:
           # Return Card objects for the buckets
           return [card1, card2]
   
   def get_brain(cfg) -> MyBrain:
       """Factory function."""
       return MyBrain()
   ```

3. **Keep stdlib-only:** No external dependencies beyond Python stdlib. (LLM calls go through elite-agent's `elite_agent/llm.py`, not in the brain.)

### Register Your Brain

Point `EA_BRAIN` to your module:
```bash
# For a package under elite_agent/brains/my_brain/
EA_BRAIN=elite_agent.brains.my_brain python3 -m elite_agent run

# For a completely external module path:
EA_BRAIN=my.custom.module python3 -m elite_agent run
```

The agent will dynamically import and call `get_brain(cfg)`.

### Test Your Brain

- Verify that `classify()` returns non-empty bucket lists for test emails
- Verify that `retrieve()` returns `Card` objects matching those buckets
- Check that `route()` produces `RouteResult` with all required fields
- Ensure your module imports without errors

### Submit a PR

If contributing your brain to this repo:
1. **Implement `BaseBrain`** in a new subpackage under `elite_agent/brains/`
2. **Write tests** in `tests/test_custom_brain.py` or similar
3. **Document the classification logic** in a comment or README within your brain package
4. **Open a PR** with an explanation of how your brain differs from Olympic (e.g., different classification strategy, custom card format)

## Code Style

- Use **type hints** (PEP 484)
- Run **pytest** before submitting (ensure all tests pass)
- Keep functions small and testable
- Document public functions and classes with docstrings

## Reporting Issues

If you find a bug or have a feature request:
1. **Search existing issues** to avoid duplicates
2. **Open an issue** with:
   - A clear title and description
   - Steps to reproduce (for bugs)
   - Expected vs. actual behavior
   - Your environment (Python version, OS, elite-agent version)
3. **For security issues**, email the maintainers privately (do not open a public issue)

Thank you for making elite-agent better!
