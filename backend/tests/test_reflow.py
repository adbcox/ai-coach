from app import convert, reflow
from tests.pdfgen import make_pdf

USER_EXAMPLE = """The use and development of wearable technology monitor -
ing fitness and activity have grown exponentially over the
last few years. In 2020, 396 million wearable units were
shipped worldwide, and it is forecasted that this will increase
up to 631.7 million units by 2024 [1]. Wearable devices give
users the opportunity to monitor health-related metrics, such
as daily steps, heart rate (HR), energy expenditure, or cardiorespiratory fitness, therefore, promoting physical activity"""


def paras(text, vocab=None):
    text = reflow.normalize(text)
    return reflow.paragraphs_from_lines(text.splitlines(), vocab if vocab is not None else reflow.vocabulary(text))


def test_the_reported_example_reads_as_one_clean_paragraph():
    out = paras(USER_EXAMPLE)
    assert len(out) == 1
    assert "monitoring fitness" in out[0] and "monitor -" not in out[0] and "\n" not in out[0]
    assert "health-related metrics" in out[0] and "631.7 million units by 2024 [1]. Wearable" in out[0]


def test_split_words_are_rejoined_and_real_compounds_keep_their_hyphen():
    v = reflow.vocabulary("cardiorespiratory fitness and high-intensity training")
    assert paras("improves cardio-\nrespiratory fitness over a long period of time in the athletes", v)[0] == \
        "improves cardiorespiratory fitness over a long period of time in the athletes"
    assert "high-intensity" in paras("a block of high-\nintensity intervals every week for the whole group", v)[0]
    assert paras("we monitor-\ning the group over a long period of time here in the lab", set())[0].startswith("we monitoring the group")  # no vocabulary: join
    assert "monitoring" in paras("we monitor ‐\ning the group over a long period of time here in the lab", set())[0]


def test_dashes_between_numbers_and_before_capitals_are_not_joined():
    assert "10 - 20 minutes" in paras("The range was 10 -\n20 minutes per session in the study group today", set())[0]
    assert "- Which" in paras("the result was clear in every athlete in the group -\nWhich is the point of it", set())[0]


def test_paragraph_breaks_follow_short_lines_and_list_items():
    text = ("Methods were applied to every athlete in the study over the whole season at the same time of day.\n"
            "Heart rate was recorded on every single run of the training block that was completed.\n"
            "Results follow here.\n"
            "The second paragraph starts here and it keeps going for a full line of text in the paper.\n"
            "1. First numbered point that is long enough to be a real line of text in this document\n"
            "2. Second numbered point that is long enough to be a real line of text in this document")
    out = paras(text)
    assert out == [
        "Methods were applied to every athlete in the study over the whole season at the same time of day. "
        "Heart rate was recorded on every single run of the training block that was completed. Results follow here.",
        "The second paragraph starts here and it keeps going for a full line of text in the paper.",
        "1. First numbered point that is long enough to be a real line of text in this document",
        "2. Second numbered point that is long enough to be a real line of text in this document"]


def test_ligatures_and_soft_hyphens():
    assert reflow.normalize("eﬃcient ﬁve ﬂow co­operate") == "efficient five flow co-operate"


def test_running_headers_and_page_numbers_are_removed():
    body = "Line one of body text that is long enough to count as a real line in this page of the paper."
    pages = [["J Appl Physiol 93: 1039-1046, 2002", body + f" Page {i} adds its own different words here.", str(1039 + i)] for i in range(4)]
    cleaned = reflow.strip_running_headers(pages)
    assert [len(p) for p in cleaned] == [1, 1, 1, 1] and all(p[0].startswith("Line one") for p in cleaned)
    short = [["J Appl Physiol", body, "7"]]
    assert reflow.strip_running_headers(short) == short           # too few pages to tell a header from content


def test_ocr_style_text_only_joins_wrapped_lines():
    text = "First paragraph wraps over two\nlines of recognised text.\n\nSecond paragraph.\n\nThird with a split mon-\nitoring word."
    out = reflow.paragraphs_from_text(text, reflow.vocabulary("monitoring"))
    assert out == ["First paragraph wraps over two lines of recognised text.", "Second paragraph.", "Third with a split monitoring word."]


def test_whole_pdf_goes_through_the_cleanup():
    lines = USER_EXAMPLE.splitlines()
    c = convert.pdf_to_markdown(make_pdf([lines + ["End of the first paragraph.", "A second paragraph that is on its own line."]]))
    assert "monitoring fitness and activity have grown exponentially over the last few years." in c.markdown
    assert "monitor -" not in c.markdown and "End of the first paragraph.\n\nA second paragraph" in c.markdown
