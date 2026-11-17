import assert from "node:assert/strict";
import {test} from "node:test";
import {chainPoints} from "../web/foundry/rigging/part-author.js";

test("subdivides a placed appendage without changing its attachment or tip", () => {
    assert.deepEqual(chainPoints([1, 2, 3], [1, 5, 0], 3), [
        [1, 2, 3], [1, 3, 2], [1, 4, 1], [1, 5, 0],
    ]);
    assert.throws(() => chainPoints([0, 0, 0], [0, 0, 0], 3), RangeError);
    assert.throws(() => chainPoints([0, 0, 0], [1, 0, 0], 33), RangeError);
});
