for path, content in [
    (f"{base_dir}/src/consistency/crdt/base.py", crdt_base),
    (f"{base_dir}/src/consistency/crdt/g_counter.py", g_counter),
    (f"{base_dir}/src/consistency/crdt/pn_counter.py", pn_counter),
    (f"{base_dir}/src/consistency/crdt/lww_register.py", lww_register),
    (f"{base_dir}/src/consistency/crdt/or_set.py", or_set),
]:
    with open(path, "w") as f:
        f.write(content)

print("✅ CRDT implementations:")
print("   - src/consistency/crdt/base.py")
print("   - src/consistency/crdt/g_counter.py")
print("   - src/consistency/crdt/pn_counter.py")
print("   - src/consistency/crdt/lww_register.py")
print("   - src/consistency/crdt/or_set.py")