from collections import deque
from dataclasses import replace
from random import Random

from app.kademlia import Complete, DHTNetwork, K, Rpc, Timer


def network(ids):
    dht = DHTNetwork(Random(161), timeout_ms=50)
    for number in ids:
        dht.add_node(f"n{number}", number)
    return dht


def introduce(dht, origin, *peers):
    for peer in peers:
        dht.nodes[origin].table.observe(dht.nodes[peer].contact, 0)


def requests(effects):
    return [e for e in effects if isinstance(e, Rpc) and not e.reply]


def answer(dht, request, now):
    reply = next(e for e in dht.receive(request, now) if isinstance(e, Rpc) and e.reply)
    return dht.receive(reply, now + 1)


def run(dht, effects, now=0):
    queue = deque(effects)
    results = []
    while queue:
        effect = queue.popleft()
        if isinstance(effect, Rpc):
            now += 1
            queue.extend(dht.receive(effect, now))
        if isinstance(effect, Complete):
            results.append(effect)
    return results


def test_query_reissues_before_slow_siblings_and_uses_local_information():
    dht = network([100, 12, 13, 14, 2, 0])
    introduce(dht, "n100", "n12", "n13", "n14")
    introduce(dht, "n12", "n2")
    outgoing = requests(dht.find_nodes("walk", "n100", 0, 0))
    assert [r.target for r in outgoing] == ["n12", "n13", "n14"]
    follow = answer(dht, outgoing[0], 3)
    assert [r.target for r in requests(follow)] == ["n2"]
    assert "n0" not in str(dht.inspect("n100", 4)["active_lookups"])
    assert dht._searches["walk"].responded == {"n12"}
    assert dht._searches["walk"].queried == {"n12", "n13", "n14", "n2"}


def test_stagnation_performs_final_sweep_and_silent_contacts_can_answer_late():
    dht = network(range(24))
    introduce(dht, "n23", *[f"n{i}" for i in range(20)])
    initial = dht.find_nodes("walk", "n23", 0, 0)
    first, second, third = requests(initial)
    assert dht.receive(replace(first, reply=True, rpc_id=first.rpc_id + 1), 1) == []
    timer = next(t for t in initial if isinstance(t, Timer) and t.rpc_id == first.rpc_id)
    assert dht.wake(timer, 49) == []
    fourth = requests(dht.wake(timer, 50))
    assert fourth[0].target == "n3"
    answer(dht, second, 51)
    remaining = requests(answer(dht, third, 52))
    assert len(remaining) > 3
    answer(dht, first, 53)
    assert "n0" in dht._searches["walk"].responded
    assert dht.wake(timer, 500) == []


def test_store_targets_twenty_closest_including_origin_and_value_lookup_is_opaque():
    dht = network(range(26))
    for node in dht.nodes.values():
        introduce(dht, node.peer_id, *[p for p in dht.nodes if p != node.peer_id])
    value = b"sealed manifest"
    result, = run(dht, dht.publish("publish", "n25", 14, value, 0))
    expected = {f"n{i}" for i in sorted(range(26), key=lambda i: i ^ 14)[:K]}
    assert result.success and set(result.peers) == expected
    assert {p for p, node in dht.nodes.items() if 14 in node.records} == expected
    origin = next(p for p in dht.nodes if p not in expected)
    value_result, = run(dht, dht.lookup("poll", origin, 14, 100), 100)
    assert value_result.value == value
    assert "sealed manifest" not in str(dht.inspect(result.peers[0], 101))
    local_result, = dht.lookup("local", result.peers[0], 14, 111)
    assert local_result.value == value


def test_all_unresponsive_times_out_once_and_keeps_local_observation():
    dht = network([1, 2])
    introduce(dht, "n1", "n2")
    outgoing = dht.lookup("poll", "n1", 12, 10)
    timer, = [e for e in outgoing if isinstance(e, Timer)]
    result, = [e for e in dht.wake(timer, 60) if isinstance(e, Complete)]
    assert result == Complete("poll", False, None, ())
    assert dht.inspect("n1", 61)["observations"]["n2"]["status"] == "unresponsive"
    assert answer(dht, requests(outgoing)[0], 62) == []
