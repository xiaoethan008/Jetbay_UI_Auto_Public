from scripts.check_artifact_layout import find_invalid_entries


def test_artifact_root_accepts_only_documented_entries(tmp_path):
    (tmp_path / "README.md").write_text("layout", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "临时文件").mkdir()
    (tmp_path / "官网V4.1.6（SOS急救类型选择）").mkdir()

    assert find_invalid_entries(tmp_path) == []


def test_artifact_root_rejects_unclassified_files_and_directories(tmp_path):
    unexpected_directory = tmp_path / "dev全量回归_20260813"
    unexpected_file = tmp_path / "country-code-debug.png"
    unexpected_directory.mkdir()
    unexpected_file.write_bytes(b"debug")

    assert set(find_invalid_entries(tmp_path)) == {
        unexpected_directory,
        unexpected_file,
    }
