from creative.source import article_text

NAV = ["صفحهٔ اصلی", "رویدادهای کنونی", "مقالهٔ تصادفی", "ورود", "فهرست"] * 16          # 80 menu nodes, as on the real page
BODY = ["بخش نخست", "این یک بند واقعی از مقاله است که دربارهٔ تنگهٔ هرمز و پیامدهای آن توضیح می‌دهد و بیش از هشتاد نویسه طول دارد. [ ۲۰ ] [ ۲۱ ]",
        "بخش دوم", "بند دوم مقاله دربارهٔ حقوق بین‌الملل و دیدگاه کارشناسان است و آن هم به‌اندازهٔ کافی بلند است تا نثر شمرده شود."]


def test_menu_is_dropped_and_article_prose_kept_with_citations_removed():
    text = article_text({"content": NAV + BODY})
    assert "صفحهٔ اصلی" not in text and "تنگهٔ هرمز" in text and "حقوق بین‌الملل" in text
    assert "[" not in text and "بخش دوم" in text            # headings between paragraphs stay


def test_old_cut_would_have_missed_the_article():
    assert not any("تنگهٔ هرمز" in item for item in (NAV + BODY)[:80])


def test_budget_is_respected_and_short_pages_still_yield_text():
    long_body = ["واژه " * 40] * 100
    assert len(article_text({"content": NAV + long_body}, limit=1000)) <= 1010
    assert "فروشگاه آنلاین لوازم ورزشی" in article_text({"content": ["منو", "فروشگاه آنلاین لوازم ورزشی ایران", "ارسال رایگان به همه شهرها"]})
