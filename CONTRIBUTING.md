# Contributing to Comfort Advisor

Everybody is invited and welcome to contribute to Comfort Advisor.

## Report bugs using Github's [issues](https://github.com/lymanepp/ha-comfort-advisor/issues)

I use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/lymanepp/ha-comfort-advisor/issues/new/choose).

## Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can.
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

People *love* thorough bug reports. I'm not even kidding.

## Any contributions you make will be under the Contributor License Agreement (CLA)

In short, when you submit code changes, your submissions are understood to be under [Contributor License Agreement (CLA)](CLA.md) that covers the project. Feel free to contact the maintainers if that's a concern.

## Pull Requests

1. Fork the repo and create your branch from `master`.
2. Make sure you have pre-commit installed and run `pre-commit install`.
3. If you've added code that should be tested, add tests.
4. If you've changed APIs, update the documentation.
5. Ensure the [test suite](#test-suite) passes.
6. Make sure your code [lints](#style-guideline).
7. Issue that pull request!

## Test Suite

Install the integration's runtime and test dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements_test.txt
```

When changing the algorithms alongside the integration, install the sibling
library checkout after installing the pinned dependencies:

```bash
python -m pip install -e ../comfort-advisor
python -m pytest
```

Keep the local library version aligned with the integration's manifest pin during
development so Home Assistant accepts the editable install. For integration-only
work, run the same pytest command with the pinned dependency.

Put algorithm and formula regression tests in the standalone library. Keep
algorithm configuration constants and defaults in `comfort_advisor.const` in
that library. This repository tests how Home Assistant supplies inputs and
configuration to the library and exposes its results.

Publish a library release when a deployable integration release needs library
changes. Update the pin in both the integration manifest and `requirements.txt`,
then run the integration suite against the published version.

## Style Guideline

We use [home assistants style guideline](https://developers.home-assistant.io/docs/development_guidelines).

## Contributor Credits

You can add yourself to [CREDITS.md](CREDITS.md) in your PR. Otherwise you will be added before our next release.
