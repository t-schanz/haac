from unittest.mock import patch
from haac.cli import main


def test_no_command_exits():
    with patch("haac.cli.sys.argv", ["haac"]):
        try:
            main()
        except SystemExit as e:
            assert e.code == 2


def test_missing_url_exits():
    with patch("haac.cli.sys.argv", ["haac", "plan"]), \
         patch("haac.cli.load_config") as mock_config:
        mock_config.return_value.ha_url = ""
        mock_config.return_value.ha_token = "token"
        try:
            main()
        except SystemExit as e:
            assert e.code == 1


def test_missing_token_exits():
    with patch("haac.cli.sys.argv", ["haac", "plan"]), \
         patch("haac.cli.load_config") as mock_config:
        mock_config.return_value.ha_url = "http://ha:8123"
        mock_config.return_value.ha_token = ""
        try:
            main()
        except SystemExit as e:
            assert e.code == 1
