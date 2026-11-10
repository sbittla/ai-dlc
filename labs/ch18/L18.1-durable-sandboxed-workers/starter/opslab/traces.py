"""One job, traced end to end, and where its time went. TODO 5 is `breakdown`.

`traced_baseline` runs drill F0 with Chapter 16's tracer on the simulated clock: the request that asked for the
work is a span, each attempt at the job is a `process_job` span linked to it, and each tool call is a child of
its attempt. The job's own events (enqueued, claimed, waiting, woken, done) come from the queue.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .world import World
from relay.telemetry import MemoryExporter, Tracer
from relay.telemetry.trace import IdSource, format_traceparent


def traced_baseline() -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="lab18-trace-"))
    try:
        exporter = MemoryExporter()
        world = World(tmp)
        tracer = Tracer(exporter, IdSource(seed=1803), clock_ns=lambda: int(world.clock.t * 1_000_000_000))
        world.tracer = tracer
        request = tracer.start("POST /v1/spec-to-pr-requests")
        world.enqueue(traceparent=format_traceparent(request))
        tracer.end(request)
        world.clock.t += 3  # the worker's next poll
        worker = world.worker()
        assert worker.run_once() == "waiting"
        world.clock.t += 600  # the requester reads the diff and approves
        world.approve_and_wake()
        world.clock.t += 2
        assert worker.run_once() == "done"
        events = world.queue.events(1)
        spans = [{"name": s.name, "trace_id": s.trace_id, "span_id": s.span_id, "parent": s.parent_span_id,
                  "links": [link["span_id"] for link in s.links], "start_s": s.start_ns / 1e9,
                  "end_s": s.end_ns / 1e9, "events": [e["name"] for e in s.events]} for s in exporter.spans]
        return {"events": events, "spans": spans, "request_span": request.span_id}
    finally:
        import gc
        gc.collect()
        shutil.rmtree(tmp, ignore_errors=True)


def breakdown(events: list[dict], spans: list[dict]) -> dict:
    """TODO 5. Where one job's time went, in seconds, from its queue events and its spans.

    - queue_wait: from the "enqueued" event to the first "claimed" event;
    - approval_wait: the sum, over each "waiting" event, of the time until the next "woken" event;
    - agent: the sum of the durations (end_s - start_s) of the spans named "process_job ..." ;
    - tests: the sum of the durations of the spans named "execute_tool run_tests" (a tool span runs from its
      step to the next one, so it includes the model call that follows);
    - total: from "enqueued" to the last "done" event;
    - attempts: the number of "process_job" spans; tool_calls: the number of "execute_tool" spans;
    - linked: True if every "process_job" span has at least one link.
    Round seconds to one decimal place.
    """
    raise NotImplementedError("TODO 5")
