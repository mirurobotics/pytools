from pytools.services.lint.linter.analysis.comments import collect_comments

_SOURCE = """\
# top
x = "# not a comment"  # trailing

def f():
    # inside
    return 1
# spaced \t
"""


def test_collect_comments_maps_lines_to_comments() -> None:
    assert collect_comments(_SOURCE) == {
        1: "# top",
        2: "# trailing",
        5: "# inside",
        7: "# spaced",
    }
