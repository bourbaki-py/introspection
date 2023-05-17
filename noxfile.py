"""Nox sessions."""
import nox
from nox.sessions import Session

nox.options.sessions = "lint", "mypy", "tests"

PACKAGE = "bourbaki-introspection"
LOCATIONS = "src", "tests", "./noxfile.py"
PYTHON = "3.11"
PYTHONS = ["3.11", "3.10", "3.9", "3.8", "3.7"]


# Formatting


@nox.session(python=PYTHON)
def isort(session: Session) -> None:
    """Run isort import formatter."""
    args = session.posargs or LOCATIONS
    session.run("poetry", "install", "--only", "isort", external=True)
    session.run("isort", *args)


@nox.session(python=PYTHON)
def black(session: Session) -> None:
    """Run black code formatter."""
    args = session.posargs or LOCATIONS
    session.run("poetry", "install", "--only", "black", external=True)
    session.run("black", *args)


# Linting


@nox.session(python=PYTHONS)
def lint(session: Session) -> None:
    """Lint using flake8."""
    args = session.posargs or LOCATIONS
    session.run("poetry", "install", "--only", "lint", external=True)
    session.run("flake8", *args)


# Typechecking


@nox.session(python=PYTHONS)
def mypy(session: Session) -> None:
    """Type-check using mypy."""
    args = session.posargs or LOCATIONS
    session.run("poetry", "install", "--only", "main,mypy", external=True)
    session.run("mypy", *args)


# Testing


@nox.session(python=PYTHONS)
def tests(session: Session) -> None:
    """Run the test suite."""
    args = session.posargs or ["-rxs", "--cov"]
    session.run("poetry", "install", "--only", "main,test", external=True)
    session.run("pytest", *args)
