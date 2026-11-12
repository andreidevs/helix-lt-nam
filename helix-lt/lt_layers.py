"""Light captures on the LT (lt_port.py --layers): the kernel skips the layers a capture leaves empty
(IR word 7), and four NAM blocks (23 / 20 / 16 / 14 layers), each its own model, DSP cost and layer limit.
Generated from the tree the hardware build was made in; every replacement must match exactly once."""

PATCHES = [
    ('nam_floor5.py',
     '\n'
     'def kernel_src():\n',
     '\n'
     '# Light captures (LAYERS): a capture distilled to its first P layers is stored as a full A2 Lite whose\n'
     '# layers P..22 are all zero (bit for bit the same output: a zero layer adds exactly 0 to x and to the\n'
     "# head's sum). The converter writes P / 32 into the User IR's header word 7 (0 in every older IR: all\n"
     '# 23 layers). The load keeps 23 - P in the slot (S_NSKIP); a layer at or past P is not computed, but\n'
     "# everything the DMA queue counts still happens: a far layer's taps are waited for and copied (fwait,\n"
     '# fcopy) and every layer bumps EVENTS, so the queue, its thresholds and its buffers run as for 23.\n'
     'LAYER_PATCHES = [\n'
     '    ("""      IF NE JUMP n_lskip;               // (their loop counts and pointers come from the row)\n'
     '""", """      IF NE JUMP n_lskip;               // (their loop counts and pointers come from the row)\n'
     "      R0 = DM(T_LW, I4);                // S_LW + this layer's index\n"
     '      R1 = DM(S_NSKIP, I6);             // + the layers the capture leaves empty\n'
     '      R0 = R0 + R1;\n'
     '      R1 = S_LW + NLAYERS;\n'
     '      COMP(R0, R1);\n'
     '      IF GE JUMP n_skip;                // at or past its last layer: not computed\n'
     '"""),\n'
     '    ("""n_ddr:\n'
     '      CALL fwait;\n'
     '      CALL fcopy;\n'
     '""", """n_skip:                                 // an empty layer: nothing computed. A far one\'s taps are\n'
     '      R0 = DM(T_FAR, I4);               // never fetched (pump marks the job done), but fwait still\n'
     '      R0 = PASS R0;                     // waits for the queue to pass it (the jobs before it, the\n'
     "      IF EQ JUMP n_lev;                 // last group's write-back from OUTBUF included, ended), and\n"
     '      CALL fwait;                       // fcopy still fills OUTBUF and the write address and counts\n'
     '      CALL fcopy;                       // its event (a group with a computed layer still writes back)\n'
     '      JUMP n_lev;\n'
     'n_ddr:\n'
     '      CALL fwait;\n'
     '      CALL fcopy;\n'
     '"""),\n'
     '    ("""      I4 = R15;\n'
     '      L0 = 0;\n'
     '      L1 = 0;\n'
     '      L2 = 0;\n'
     '""", """      I4 = R15;\n'
     'n_lev:\n'
     '      L0 = 0;\n'
     '      L1 = 0;\n'
     '      L2 = 0;\n'
     '"""),\n'
     '    ("""    R0 = R0 + 1;\n'
     '    DM(J_NEXT) = R0;\n'
     '    R0 = 1;\n'
     '    DM(J_BUSY) = R0;\n'
     '""", """    R0 = R0 + 1;\n'
     '    DM(J_NEXT) = R0;\n'
     "    R1 = DM(J_TYPE, I5);                // a far layer's taps (0) or a group's write-back (1),\n"
     "    R1 = R1 - 1;                        // from an empty layer on: done, never run (the queue's\n"
     '    IF GT JUMP p_run;                   // order and J_DONE as if it had run)\n'
     '    I3 = DM(J_ROW, I5);\n'
     '    R1 = DM(T_LW, I3);\n'
     '    R2 = DM(S_NSKIP, I6);\n'
     '    R1 = R1 + R2;\n'
     '    R2 = S_LW + NLAYERS;\n'
     '    COMP(R1, R2);\n'
     '    IF LT JUMP p_run;\n'
     '    R1 = DM(J_DONE);\n'
     '    R1 = R1 + 1;\n'
     '    DM(J_DONE) = R1;\n'
     '    JUMP p_next;\n'
     'p_run:\n'
     '    R0 = 1;\n'
     '    DM(J_BUSY) = R0;\n'
     '"""),\n'
     '    ("""    DM(S_TRIM, I6) = F0;\n'
     '""", """    DM(S_TRIM, I6) = F0;\n'
     "    CALL ld_layers;                     // word 7: the capture's layer count\n"
     '"""),\n'
     '    ("""    DM(S_FRESH, I6) = R1;               // no tail: nothing played before\n'
     '""", """    DM(S_FRESH, I6) = R1;               // no tail: nothing played before\n'
     '    DM(S_NSKIP, I6) = R0;               // all layers until a model loads\n'
     '"""),\n'
     "    # the block's limit: a capture with more layers than its block's P_LIM (a constant its model's\n"
     '    # graph sets at creation, pid P_LIM; 0: none) is refused as no capture (silence), so a block\n'
     '    # never runs above the DSP cost its model declares\n'
     '    ("""    F2 = DM(-4, I3);\n'
     '    F3 = 1.8271484375;                  // 1871 / 1024\n'
     '    COMP(F2, F3);\n'
     '    IF NE JUMP n_none;\n'
     '""", """    F2 = DM(-4, I3);\n'
     '    F3 = 1.8271484375;                  // 1871 / 1024\n'
     '    COMP(F2, F3);\n'
     '    IF NE JUMP n_none;\n'
     "    F2 = DM(-7, I3);                    // the capture's layers: word 7 x 32 (0: all 23)\n"
     '    F3 = 32.0;\n'
     '    F2 = F2 * F3;\n'
     '    R2 = FIX F2;\n'
     '    R3 = NLAYERS;\n'
     '    R2 = PASS R2;\n'
     '    IF LE R2 = PASS R3;\n'
     "    R0 = DM(P_LIM, I0);                 // the block's limit, LIM_TAG | n; anything else (the\n"
     "    R3 = LIM_TAG;                       // instance's memory is not cleared): none\n"
     '    R0 = R0 XOR R3;\n'
     '    R3 = 0xFF;\n'
     '    COMPU(R0, R3);\n'
     '    IF GT JUMP n_lok;\n'
     '    COMP(R2, R0);\n'
     '    IF GT JUMP n_none;                  // more layers than the block runs\n'
     'n_lok:\n'
     '"""),\n'
     ']\n'
     "P_LIM = 16                              # the instance word (pid) of the block's layer limit\n"
     'LIM_TAG = 0x4E4C0000                    # its value: LIM_TAG | the most layers the block runs\n'
     'LAYER_SUB = """\n'
     "// IR word 7 (I3 = the slot's top word): the capture's layer count P / 32; 0 in older IRs. The slot keeps\n"
     '// 23 - P, 0 (all layers) for 0 or for anything outside 1..23. Uses R0-R2, F0, F1.\n'
     'ld_layers:\n'
     '    F0 = DM(-7, I3);\n'
     '    F1 = 32.0;\n'
     '    F0 = F0 * F1;\n'
     '    R0 = FIX F0;\n'
     '    R1 = NLAYERS;\n'
     '    R2 = R1 - R0;\n'
     '    R0 = PASS R0;\n'
     '    IF LE R2 = R2 - R2;\n'
     '    R2 = PASS R2;\n'
     '    IF LT R2 = R2 - R2;\n'
     '    DM(S_NSKIP, I6) = R2;\n'
     '    RTS;\n'
     '"""\n'
     '\n'
     '\n'
     'def kernel_src():\n',
     1),
    ('nam_floor5.py',
     '        src = src.replace(a, MP_SUB + a)\n'
     '    if P9_SHARE and not KEEP_POLLS:      # room for it: the wait-poll count (REP R_POLLS /\n',
     '        src = src.replace(a, MP_SUB + a)\n'
     '    if LAYERS:\n'
     '        for a, b in LAYER_PATCHES:\n'
     '            assert src.count(a) == 1, a[:70]\n'
     '            src = src.replace(a, b)\n'
     '        a = "\\nlwait:\\n"\n'
     '        assert src.count(a) == 1\n'
     '        src = src.replace(a, LAYER_SUB + a)\n'
     '    if P9_SHARE and not KEEP_POLLS:      # room for it: the wait-poll count (REP R_POLLS /\n',
     1),
    ('nam_floor5.py',
     'GATHER = os.environ.get("NAM_GATHER") == "1"\n'
     "PRB_WORDS = 0                       # (nam_floor5t: the tap-list probe's buffer)\n",
     'GATHER = os.environ.get("NAM_GATHER") == "1"\n'
     'LAYERS = os.environ.get("NAM_LAYERS") == "1"   # skip the layers a light capture leaves empty (IR word 7)\n'
     "PRB_WORDS = 0                       # (nam_floor5t: the tap-list probe's buffer)\n",
     1),
    ('nam_floor5.py',
     '                         "S_PMB", "INST_DM_SPAN", "INST_PM_SPAN"] + \\\n',
     '                         "S_PMB", "INST_DM_SPAN", "INST_PM_SPAN"] + (["S_NSKIP", "P_LIM", "LIM_TAG"] if LAYERS else []) + \\\n',
     1),
    ('nam_floor5.py',
     '        o += o & 1\n'
     '        self.slot_size = o\n',
     '        o += o & 1\n'
     "        self.s_nskip = o                 # (LAYERS) how many trailing layers the slot's capture leaves empty\n"
     '        o += 2 if LAYERS else 0\n'
     '        self.slot_size = o\n',
     1),
    ('nam_floor5.py',
     '                 **({"PRB": alloc["PRB"]} if PRB_WORDS else {}))\n'
     '        self.v = v\n',
     '                 **({"PRB": alloc["PRB"]} if PRB_WORDS else {}))\n'
     '        v["S_NSKIP"], v["P_LIM"], v["LIM_TAG"] = self.s_nskip, P_LIM, LIM_TAG\n'
     '        self.v = v\n',
     1),
    ('stage_model.py',
     'pa.nam_host_member = nam_host_member\n'
     'add_model_entry3 = _floor_copy(pa.add_model_entry3)\n',
     'pa.nam_host_member = nam_host_member\n'
     '\n'
     '# LAYERS: four NAM blocks on the one kernel, each its own model (and DSP cost, stage_main), its graph\n'
     '# setting the instance word P_LIM to LIM_TAG | the most layers a capture in it may have (nam_floor5).\n'
     '# (internal name, display name, layer limit); the first is the NAM block of the plain build: presets keep it.\n'
     'NAM_MODELS = [("HD2_AmpNAMLite", "NAM A2 Lite", 23)] + (\n'
     '    [("HD2_AmpNAMLite20", "NAM Lite 20", 20), ("HD2_AmpNAMLite16", "NAM Lite 16", 16),\n'
     '     ("HD2_AmpNAMLite14", "NAM Lite 14", 14)] if getattr(nam_floor, "LAYERS", False) else [])\n'
     '_CONSTS = []                               # (pid, word): what the next nam_host_blob adds as member inits\n'
     '\n'
     '\n'
     'def nam_host_blob(comp_id, params):\n'
     '    """Upstream\'s, plus a member init (kind 2, member 1) for each of _CONSTS: a constant the loader\n'
     '    passes to the member\'s control handler at creation, as stock blobs set their members\' constants."""\n'
     '    consts = list(_CONSTS)\n'
     '    n, m = len(params), 2 * len(params) + len(consts)\n'
     '    a_off = 0x18\n'
     '    data_off = a_off + 10 * 2 * n\n'
     '    c_off = data_off + 3 * n\n'
     '    d_off = c_off + 4 * n\n'
     '    e_off = d_off + 4 * n\n'
     '    end = e_off + 4 * n\n'
     '    pm = [a_off, 0, c_off, 0, c_off, 0, d_off, 0, e_off, 0, end, 0]\n'
     '    pm += [5 * n, 2 * n, 3 * n, 3 * n, n, n]\n'
     '    pm += [2 * n, 0, n, n, n, 0]\n'
     '    for k, p in enumerate(params):\n'
     "        pm += [data_off, 0, k, p['op'], 1, 2, 0, 0, 1, 0]\n"
     '    for k in range(n):\n'
     '        pm += [data_off + 3 * k, 0, n + k, 1, 0, 3, 3, 3, 0, 0]\n'
     '    for p in params:\n'
     "        pm += [0x0e, p['pid'], 1]\n"
     '    for k in range(n):\n'
     '        pm += [k, n + k, 0, 0]\n'
     "    for k, p in sorted(enumerate(params), key=lambda kp: kp[1]['slot']):\n"
     "        pm += [k, k, p['slot'], 0]\n"
     '    for k in range(n):\n'
     '        pm += [k, k, k, 0]\n'
     '    assert len(pm) == end\n'
     '    v0 = 0x10\n'
     '    tree = v0 + 2 * m\n'
     '    pmo = tree + 4\n'
     '    pin = pmo + len(pm)\n'
     '    ini = pin + 4 * m\n'
     '    sub = ini + 2 * (n + m)\n'
     '    b = [3, 2, tree, 1, ini, n + m, pmo, len(pm), sub, 0, pin, m]\n'
     '    b += [1, 0, 1, 2]\n'
     '    for p in params + params:\n'
     "        b += [1, p['default_word']]\n"
     '    for _, w in consts:\n'
     '        b += [1, w]\n'
     '    b += [0, comp_id, 0, 0]\n'
     '    b += pm\n'
     '    for k, p in enumerate(params):\n'
     "        b += [0x0c, p['slot'], v0 + 2 * k, 1]\n"
     '    for k, p in enumerate(params):\n'
     "        b += [0x0e, p['pid'], v0 + 2 * (n + k), 2]\n"
     '    for j, (pid, _) in enumerate(consts):\n'
     '        b += [0x0e, pid, v0 + 2 * (2 * n + j), 2]\n'
     '    for k in range(n):\n'
     '        b += [1, pmo + data_off + 3 * k]\n'
     '    for k in range(m):\n'
     '        b += [1, pin + 4 * k]\n'
     '    assert len(b) == sub\n'
     '    return b\n'
     '\n'
     '\n'
     '_upstream_blob = pa.nam_host_blob\n'
     'pa.nam_host_blob = nam_host_blob\n'
     'add_model_entry3 = _floor_copy(pa.add_model_entry3)\n',
     1),
    ('stage_model.py',
     "    new_gl, blob_idx, comp = add_model_entry4(e_gl, clarity['blob_index'], nam, SDRAM_WORDS)\n"
     "    new_db, model_id, lists = add_model_entry3(e_db, clarity, 'HD2_AmpNAMLite', 'NAM A2 Lite', blob_idx, nam)\n",
     '    _CONSTS.clear()\n'
     '    assert nam_host_blob(0x600123, nam) == _upstream_blob(0x600123, nam), "nam_host_blob differs from upstream\'s"\n'
     '    new_gl, new_db, added = e_gl, e_db, []\n'
     '    for name, disp, lim in NAM_MODELS:\n'
     '        _CONSTS[:] = [(nam_floor.P_LIM, nam_floor.LIM_TAG | lim)] if len(NAM_MODELS) > 1 else []\n'
     "        new_gl, blob_idx, comp = add_model_entry4(new_gl, clarity['blob_index'], nam, SDRAM_WORDS)\n"
     '        new_db, model_id, lists = add_model_entry3(new_db, clarity, name, disp, blob_idx, nam)\n'
     '        added.append((disp, model_id, blob_idx, comp, lim))\n',
     1),
    ('stage_model.py',
     "    assert len(chk['models']) == N_MODELS + 1 and chk['models'][-1]['name'] == 'HD2_AmpNAMLite'\n",
     "    assert [m['name'] for m in chk['models'][N_MODELS:]] == [n for n, _, _ in NAM_MODELS]\n",
     1),
    ('stage_model.py',
     '    print(f"model DB: \'NAM A2 Lite\' = model {model_id} on blob {blob_idx}, in browser groups {lists}")\n'
     '    print(f"graph library: host composite {comp:#x} (a copy of 0x6001aa), member 1 = primitive {HOOK_ID:#x}; "\n'
     '          f"Blob 0 {BLOB0_STOCK:#x} -> {len(b0):#x} words (cap {BLOB0_CAP:#x}), SHARC relocation check OK")\n',
     '    for disp, model_id, blob_idx, comp, lim in added:\n'
     '        print(f"model DB: \'{disp}\' = model {model_id} on blob {blob_idx}, host composite {comp:#x} (a copy of "\n'
     '              f"0x6001aa), member 1 = primitive {HOOK_ID:#x}" + (f"; P_LIM init {lim} layers" if len(added) > 1 else ""))\n'
     '    print(f"graph library: Blob 0 {BLOB0_STOCK:#x} -> {len(b0):#x} words (cap {BLOB0_CAP:#x}), SHARC relocation check OK")\n',
     1),
    ('stage_main.py',
     "NAME, DISPLAY, SHORT, FOLDER = 'HD2_AmpNAMLite', 'NAM A2 Lite', 'NAM A2 Lite', (12, 'NAM')\n"
     '\n',
     "NAME, DISPLAY, SHORT, FOLDER = 'HD2_AmpNAMLite', 'NAM A2 Lite', 'NAM A2 Lite', (12, 'NAM')\n"
     "# LAYERS (stage_model.NAM_MODELS): each NAM block's cost from the LT meter (2026-11-12, ~100 units a 1%:\n"
     "# 23 layers 36.2%, 20 32.8%, 16 29.2%, 14 27.5% of a block's cycles)\n"
     'LAYER_COSTS = {"HD2_AmpNAMLite": 3650, "HD2_AmpNAMLite20": 3300, "HD2_AmpNAMLite16": 2950, "HD2_AmpNAMLite14": 2770}\n'
     '\n',
     1),
    ('stage_main.py',
     'def tables(im, src_ni, new_ni, n_params):\n'
     '    """The new Table 1, Table 2 and browser lists (upstream add_model_entry0\'s steps 1-3)."""\n',
     'def tables(im, src_ni, models, n_params):\n'
     '    """The new Table 1, Table 2 and browser lists (upstream add_model_entry0\'s steps 1-3), one row and\n'
     '    one browser item each for `models`, [(model ni, display name, DSP cost)]."""\n',
     1),
    ('stage_main.py',
     '    assert new_ni not in [r[0] for r in rows]\n',
     '    assert not {ni for ni, _, _ in models} & {r[0] for r in rows}\n',
     1),
    ('stage_main.py',
     '    pid = free[0]\n'
     "    t1 += struct.pack('<IHHI', new_ni, pid, 0, DSP_COST)\n"
     '    log.append(f"Table 1: {n1} -> {n1 + 1} rows; NAM preset id {pid} (free: {free[:8]}...), DSP cost {DSP_COST} "\n'
     '               f"(Clarity {src[3]})")\n',
     '    # (the IR-title cave compares preset ids by cmp r3, #id: each must be a Thumb-2 immediate; the first,\n'
     "    # the plain build's NAM block, is free[0] as there, so its presets keep working)\n"
     '    pids = [p for p in free if p < 256 or pa._thumb_modimm(p) is not None][:len(models)]\n'
     '    assert pids[0] == free[0] and len(pids) == len(models), (pids, free[:8])\n'
     '    for (ni, disp, cost), pid in zip(models, pids):\n'
     "        t1 += struct.pack('<IHHI', ni, pid, 0, cost)\n"
     '        log.append(f"Table 1: \'{disp}\' preset id {pid}, DSP cost {cost} (Clarity {src[3]})")\n'
     '    log.append(f"Table 1: {n1} -> {n1 + len(models)} rows (free preset ids were {free[:8]}...)")\n',
     1),
    ('stage_main.py',
     "    row = bytearray(next(t2[44 * i: 44 * i + 44] for i in range(n2) if struct.unpack_from('<I', t2, 44 * i)[0] == src_ni))\n"
     "    struct.pack_into('<I', row, 0, new_ni)\n"
     "    row[4:20] = SHORT.encode('latin1')[:16].ljust(16, b'\\0')\n"
     "    counts = struct.unpack_from('<3I', row, 24)\n"
     '    assert len(set(counts)) == 1\n'
     "    struct.pack_into('<3I', row, 24, n_params, n_params, n_params)\n"
     '    t2 += row\n'
     '    log.append(f"Table 2: {n2} -> {n2 + 1} rows")\n'
     "    dname = DISPLAY.encode('latin1')[:25].ljust(26, b'\\0')\n"
     '    lists, folder_item = [], None\n',
     "    srow = bytes(next(t2[44 * i: 44 * i + 44] for i in range(n2) if struct.unpack_from('<I', t2, 44 * i)[0] == src_ni))\n"
     '    for ni, disp, _ in models:\n'
     '        row = bytearray(srow)\n'
     "        struct.pack_into('<I', row, 0, ni)\n"
     "        row[4:20] = disp.encode('latin1')[:16].ljust(16, b'\\0')\n"
     "        counts = struct.unpack_from('<3I', row, 24)\n"
     '        assert len(set(counts)) == 1\n'
     "        struct.pack_into('<3I', row, 24, n_params, n_params, n_params)\n"
     '        t2 += row\n'
     '    log.append(f"Table 2: {n2} -> {n2 + len(models)} rows")\n'
     '    lists, folder_items = [], None\n',
     1),
    ('stage_main.py',
     '        item = None\n',
     '        items = None\n',
     1),
    ('stage_main.py',
     '                item = bytearray(raw[48 * k: 48 * k + 48])\n'
     "                struct.pack_into('<IIiH', item, 0, bt, new_ni, ci, pid if ci == -1 else u12)\n"
     '                item[14:40] = dname\n'
     "                struct.pack_into('<2I', item, 40, 1, 0)\n",
     "                items = b''\n"
     '                for (ni, disp, _), pid in zip(models, pids):\n'
     '                    item = bytearray(raw[48 * k: 48 * k + 48])\n'
     "                    struct.pack_into('<IIiH', item, 0, bt, ni, ci, pid if ci == -1 else u12)\n"
     "                    item[14:40] = disp.encode('latin1')[:25].ljust(26, b'\\0')\n"
     "                    struct.pack_into('<2I', item, 40, 1, 0)\n"
     '                    items += item\n',
     1),
    ('stage_main.py',
     '        if item is None:\n',
     '        if items is None:\n',
     1),
    ('stage_main.py',
     '            if folder_item is None and ci == -1:\n'
     '                folder_item = bytes(item)\n',
     '            if folder_items is None and ci == -1:\n'
     '                folder_items = items\n',
     1),
    ('stage_main.py',
     '            lists.append((idx, lc + 1, bytes(raw + item)))\n'
     '            log.append(f"browser list ({idx // 4},{idx % 4}): {lc} -> {lc + 1} items")\n',
     '            lists.append((idx, lc + len(models), bytes(raw + items)))\n'
     '            log.append(f"browser list ({idx // 4},{idx % 4}): {lc} -> {lc + len(models)} items")\n',
     1),
    ('stage_main.py',
     '    assert folder_item is not None\n'
     '    lists.append((4 * cat + nsub, 1, folder_item))\n'
     '    log.append(f"new folder \'{fname}\' = subcategory {nsub} of category {cat}, 1 item")\n'
     '    return pid, (rd_cnt, n1 + 1, bytes(t1)), (rd2, n2 + 1, bytes(t2)), lists, (cat, nsub, fb), log\n',
     '    assert folder_items is not None\n'
     '    lists.append((4 * cat + nsub, len(models), folder_items))\n'
     '    log.append(f"new folder \'{fname}\' = subcategory {nsub} of category {cat}, {len(models)} items")\n'
     '    return pids, (rd_cnt, n1 + len(models), bytes(t1)), (rd2, n2 + len(models), bytes(t2)), lists, (cat, nsub, fb), log\n',
     1),
    ('stage_main.py',
     'def build_e0(e0, src_ni, new_ni, n_params):\n',
     'def build_e0(e0, src_ni, models, n_params):\n',
     1),
    ('stage_main.py',
     '    pid, (rd1, c1, t1), (rd2, c2, t2), lists, (cat, nsub, fb), log = tables(im, src_ni, new_ni, n_params)\n',
     '    pids, (rd1, c1, t1), (rd2, c2, t2), lists, (cat, nsub, fb), log = tables(im, src_ni, models, n_params)\n',
     1),
    ('stage_main.py',
     '    tcode, ca, cb = ir_title.build(title_base, [pid])\n',
     '    tcode, ca, cb = ir_title.build(title_base, pids)\n',
     1),
    ('stage_main.py',
     '               f"{ir_title.SITE_B:#x} (via relay {ir_title.RELAY:#x}) for preset id {pid}")\n',
     '               f"{ir_title.SITE_B:#x} (via relay {ir_title.RELAY:#x}) for preset ids {pids}")\n',
     1),
    ('stage_main.py',
     '    return out, pid, log, (a1, a2, la, ca, cb, tcode)\n',
     '    return out, pids, log, (a1, a2, la, ca, cb, tcode)\n',
     1),
    ('stage_main.py',
     'def verify(e0, src_ni, new_ni, addrs):\n',
     'def verify(e0, src_ni, models, addrs):\n',
     1),
    ('stage_main.py',
     '    assert pa._decode_thumb_movw(im.rd(TAB1_CNT_INSN, 4))[1] == 824 and im.u32(TAB1_END_PTR) == a1 + 12 * 824\n'
     '    assert im.u32(TAB2_BASE_PTR) == a2 and pa._decode_thumb_movw(im.rd(TAB2_CNT_INSN, 4))[1] == 824\n'
     "    assert struct.unpack_from('<I', im.rd(a1 + 12 * 823, 12))[0] == new_ni\n"
     "    assert struct.unpack_from('<I', im.rd(a2 + 44 * 823, 44))[0] == new_ni\n",
     '    n = 823 + len(models)\n'
     '    assert pa._decode_thumb_movw(im.rd(TAB1_CNT_INSN, 4))[1] == n and im.u32(TAB1_END_PTR) == a1 + 12 * n\n'
     '    assert im.u32(TAB2_BASE_PTR) == a2 and pa._decode_thumb_movw(im.rd(TAB2_CNT_INSN, 4))[1] == n\n'
     '    for k, (ni, _, cost) in enumerate(models):\n'
     "        r = struct.unpack_from('<IHHI', im.rd(a1 + 12 * (823 + k), 12))\n"
     '        assert (r[0], r[3]) == (ni, cost), r\n'
     "        assert struct.unpack_from('<I', im.rd(a2 + 44 * (823 + k), 44))[0] == ni\n",
     1),
    ('stage_main.py',
     "        assert struct.unpack_from('<I', im.rd(va + 48 * (cnt - 1), 48), 4)[0] == new_ni\n",
     "        assert [struct.unpack_from('<I', im.rd(va + 48 * (cnt - len(models) + k), 48), 4)[0]\n"
     '                for k in range(len(models))] == [ni for ni, _, _ in models]\n',
     1),
    ('stage_main.py',
     '    nam = pa.find_model(db, NAME)\n'
     '    assert nam[\'name\'] == NAME, "run stage_model first"\n'
     "    new_ni, n_params = nam['words'][2], len(nam['params'])\n",
     '    import stage_model\n'
     '    models = []\n'
     '    for name, disp, _ in stage_model.NAM_MODELS:\n'
     '        nam = pa.find_model(db, name)\n'
     '        assert nam[\'name\'] == name, "run stage_model first"\n'
     '        cost = LAYER_COSTS[name] if len(stage_model.NAM_MODELS) > 1 else DSP_COST\n'
     "        models.append((nam['words'][2], disp, cost))\n"
     "        assert len(nam['params']) == len(pa.find_model(db, NAME)['params'])\n"
     "    n_params = len(nam['params'])\n",
     1),
    ('stage_main.py',
     '    new0, pid, log, addrs = build_e0(e0, src_ni, new_ni, n_params)\n'
     '    msg = verify(new0, src_ni, new_ni, addrs)\n',
     '    new0, pids, log, addrs = build_e0(e0, src_ni, models, n_params)\n'
     '    msg = verify(new0, src_ni, models, addrs)\n',
     1),
]
