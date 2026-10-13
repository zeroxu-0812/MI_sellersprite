from category_search import search, build_index, children_of, browse

# 假树：模拟 fetch_tree 返回的扁平结构
TREE = [
    {"id": "2619525011:3741271:3741281", "label": "Appliances:Dishwashers:Dishwashers",
     "nodeLabelLocale": "洗碗机", "nodeLabelPathLocale": "家电:洗碗机:洗碗机",
     "products": 598, "children": 0},
    {"id": "3741281", "label": "Portable Dishwashers",
     "nodeLabelLocale": "便携洗碗机", "nodeLabelPathLocale": "便携洗碗机",
     "products": 120, "children": 0},
    {"id": "123", "label": "Water Bottles", "nodeLabelLocale": "水瓶",
     "nodeLabelPathLocale": "水瓶", "products": 9999, "children": 0},
]


def test_search_chinese_keyword():
    hits = search("洗碗机", tree=TREE)
    # 子串匹配：命中"洗碗机"(598) + "便携洗碗机"(120)，按商品数降序
    assert len(hits) == 2
    assert hits[0]["node_path"] == "2619525011:3741271:3741281"
    assert hits[0]["product_count"] == 598
    assert hits[1]["product_count"] == 120


def test_search_english_keyword():
    hits = search("water", tree=TREE)
    assert len(hits) == 1
    assert hits[0]["node_path"] == "123"


def test_search_sorts_by_product_count():
    hits = search("dishwasher", tree=TREE)  # 命中 Dishwashers(598) + Portable(120)
    assert [h["product_count"] for h in hits] == [598, 120]


def test_search_empty_keyword():
    assert search("", tree=TREE) == []
    assert search("   ", tree=TREE) == []


def test_search_respects_limit():
    hits = search("dishwasher", tree=TREE, limit=1)
    assert len(hits) == 1


# ── 品类树下钻（build_index / children_of / browse）──
# 层级假树：A(根) > A:B > A:B:C ，另一根 D(叶子)
TREE_H = [
    {"id": "A", "label": "Appliances", "nodeLabelLocale": "家电",
     "nodeLabelPathLocale": "家电", "products": 100, "children": 1},
    {"id": "A:B", "label": "Appliances:Dishwashers", "nodeLabelLocale": "洗碗机",
     "nodeLabelPathLocale": "家电:洗碗机", "products": 50, "children": 1},
    {"id": "A:B:C", "label": "Appliances:Dishwashers:Portable", "nodeLabelLocale": "便携洗碗机",
     "nodeLabelPathLocale": "家电:洗碗机:便携", "products": 20, "children": 0},
    {"id": "D", "label": "Sports", "nodeLabelLocale": "运动",
     "nodeLabelPathLocale": "运动", "products": 200, "children": 0},
]


def test_build_index_roots_sorted_by_products():
    idx = build_index(tree=TREE_H)
    # 根 = 单段 id，按 products 降序：D(200) > A(100)
    assert [r["id"] for r in idx["roots"]] == ["D", "A"]


def test_children_of_hierarchy():
    idx = build_index(tree=TREE_H)
    assert [c["id"] for c in children_of(idx, "A")] == ["A:B"]
    assert [c["id"] for c in children_of(idx, "A:B")] == ["A:B:C"]
    # 叶子与无此节点都返空
    assert children_of(idx, "A:B:C") == []
    assert children_of(idx, "D") == []
    assert children_of(idx, "不存在的id") == []


def test_browse_drill_and_select():
    # 根层选第 2 个(A) → A 的子选第 1 个(A:B) → c 选定 A:B
    inputs = iter(["2", "1", "c"])
    name, node = browse(tree=TREE_H, _in=lambda prompt="": next(inputs))
    assert node == "A:B"
    assert "洗碗机" in name


def test_browse_back_then_select_parent():
    # 进入 A → 进入 A:B → b 返回 A → c 选定 A
    inputs = iter(["2", "1", "b", "c"])
    name, node = browse(tree=TREE_H, _in=lambda prompt="": next(inputs))
    assert node == "A"
    assert "家电" in name


def test_browse_cancel_returns_none():
    inputs = iter(["q"])
    assert browse(tree=TREE_H, _in=lambda prompt="": next(inputs)) is None


def test_browse_manual_entry():
    # m 手动 → 填 node + 回车（用 node 当名）
    inputs = iter(["m", "2619525011:3741271:3741281", ""])
    name, node = browse(tree=TREE_H, _in=lambda prompt="": next(inputs))
    assert node == "2619525011:3741271:3741281"
    assert name == "2619525011:3741271:3741281"
