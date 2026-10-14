from pedidoflow.artifacts import sha256_directory, sha256_file


def test_hash_de_diretorio_e_deterministico_e_detecta_alteracao(tmp_path):
    directory = tmp_path / "adapter"
    directory.mkdir()
    first = directory / "a.txt"
    second = directory / "sub" / "b.txt"
    second.parent.mkdir()
    first.write_text("um", encoding="utf-8")
    second.write_text("dois", encoding="utf-8")

    initial = sha256_directory(directory)

    assert initial == sha256_directory(directory)
    assert sha256_file(first) != sha256_file(second)
    second.write_text("tres", encoding="utf-8")
    assert sha256_directory(directory) != initial
