import os
import concurrent.futures

def run_batch_pipeline(tasks, worker_count=4, process_func=None):
    """
    Executes multiple VoxSync AI video processing tasks in parallel using a ThreadPoolExecutor.
    `tasks` is a list of dictionaries containing keyword arguments for `process_func`.
    """
    if process_func is None:
        raise ValueError("process_func must be provided for batch execution.")

    print("=========================================================================")
    print(f"       VOXSYNC AI - PARALLEL BATCH PROCESSING ENGINE ({len(tasks)} Tasks)")
    print(f"       Worker Pool Size: {worker_count} parallel project runners")
    print("=========================================================================\n")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_task = {
            executor.submit(process_func, **task_kwargs): task_kwargs.get("project_name") or task_kwargs.get("source_input")
            for task_kwargs in tasks
        }

        for future in concurrent.futures.as_completed(future_to_task):
            task_id = future_to_task[future]
            try:
                out_path = future.result()
                results[task_id] = {"status": "SUCCESS", "output": out_path}
                print(f"✅ [Batch Worker] Task '{task_id}' COMPLETED: {out_path}")
            except Exception as e:
                results[task_id] = {"status": "FAILED", "error": str(e)}
                print(f"❌ [Batch Worker] Task '{task_id}' FAILED: {e}")

    return results
