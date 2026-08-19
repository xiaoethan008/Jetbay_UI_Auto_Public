import pytest

from scripts.cleanup_product_test_leads import cutoff_epoch_ms


def test_cutoff_epoch_ms_uses_retention_window():
    assert cutoff_epoch_ms(6, now_seconds=1_800_000_000) == 1_799_978_400_000


def test_cutoff_epoch_ms_rejects_unsafe_window():
    with pytest.raises(ValueError, match="at least 1"):
        cutoff_epoch_ms(0, now_seconds=1_800_000_000)
