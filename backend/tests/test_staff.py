import pytest

from climaguard.blocks import SMS_ACTION
from climaguard.staff import StaffError, message, validate

OK = dict(name="  R.  Selvi ", mobile="98765 43210", district_id=1, block_ids=[1, 2], district_blocks=[1, 2, 3],
          existing_mobiles=set())


def test_valid_staff_is_cleaned():
    assert validate(**OK) == ("R. Selvi", "9876543210")
    assert validate(**OK | {"mobile": "+919876543210"})[1] == "9876543210"


@pytest.mark.parametrize("change,error", [
    ({"name": " "}, "name"),
    ({"mobile": "12345"}, "10-digit"),
    ({"mobile": "5876543210"}, "10-digit"),
    ({"existing_mobiles": {"9876543210"}}, "already registered"),
    ({"block_ids": []}, "at least one block"),
    ({"block_ids": [1, 9]}, "selected district"),
])
def test_invalid_staff_is_refused(change, error):
    with pytest.raises(StaffError, match=error):
        validate(**OK | change)


@pytest.mark.parametrize("action", ["Dengue outbreak reported here before (3×): revisit those villages first",
                                    "Dense housing: check overhead tanks", "Many young children: start with schools",
                                    "Check stored water in every house"])
def test_sms_fits_names_block_and_first_action(action):
    text = message("Very high", "Kanniyakumari", 14, "Veerakeralamputhur", action)
    assert len(text) <= 160
    assert "Veerakeralamputhur" in text
    assert any(short in text for short in SMS_ACTION.values())


def test_sms_carries_no_personal_data():
    text = message("High", "Krishnagiri", 7, "Hosur", "Check stored water in every house")
    assert not any(ch.isdigit() for ch in text.replace("7 days", ""))  # no phone numbers or case counts
