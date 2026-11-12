"""Own only experiment child processes, cancellation, timeouts and resource release."""
import os
import json
import subprocess
import time
import comfy.model_management as mm

def stop_owned_process(proc):
    if proc.poll() is not None:
        return
    if os.name=="nt":
        subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW,check=False)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

def run_process(command,cwd,env,log_path,timeout_seconds):
    flags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP if os.name=="nt" else 0
    with log_path.open("a",encoding="utf-8") as log:
        log.write("\nCOMMAND: "+json.dumps(command)+"\n");log.flush()
        proc=subprocess.Popen(command,cwd=str(cwd),env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        started=time.monotonic()
        try:
            while proc.poll() is None:
                mm.throw_exception_if_processing_interrupted()
                if time.monotonic()-started>timeout_seconds:
                    raise TimeoutError("Reconstruction reached the selected time limit. Partial cache and log are preserved for inspection.")
                time.sleep(0.5)
            if proc.returncode:
                tail=log_path.read_text(encoding="utf-8",errors="replace")[-2200:]
                raise RuntimeError(f"Reconstruction exited with code {proc.returncode}. Saved log: {log_path}\n{tail}")
        finally:
            stop_owned_process(proc)


def release_models():
    mm.unload_all_models()
    mm.soft_empty_cache()
