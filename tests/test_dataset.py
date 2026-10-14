from training.generate_dataset import generate_split


def test_splits_sinteticos_nao_repetem_entradas():
    for offset, (split, size) in enumerate(
        (("train", 2400), ("validation", 300), ("test", 600))
    ):
        rows = generate_split(split, size, 42 + offset)
        inputs = [row["input"] for row in rows]

        assert len(rows) == size
        assert len(inputs) == len(set(inputs))
