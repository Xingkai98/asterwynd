from agent.branding import BRAND_NAME, SLOGAN_EN, SLOGAN_ZH, render_tui_banner


def test_render_tui_banner_uses_wide_wordmark_for_wide_terminals():
    banner = render_tui_banner(columns=120)

    assert BRAND_NAME == "Asterwynd"
    assert "█████" in banner
    assert "ASTERWYND\n" not in banner
    assert SLOGAN_EN in banner
    assert SLOGAN_ZH in banner


def test_render_tui_banner_uses_compact_wordmark_for_narrow_terminals():
    banner = render_tui_banner(columns=60)

    assert banner.startswith("ASTERWYND\n")
    assert SLOGAN_EN in banner
    assert SLOGAN_ZH in banner
