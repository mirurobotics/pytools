from pytools.services.lint.linter.analysis.comments import Comment, collect_comments

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
        1: Comment(0, "# top"),
        2: Comment(23, "# trailing"),
        5: Comment(4, "# inside"),
        7: Comment(0, "# spaced \t"),
    }
