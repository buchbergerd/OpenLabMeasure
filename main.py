from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, List
from datetime import datetime, timedelta
import asyncio
import os
import subprocess
from typing import List
import json
from concurrent.futures import ThreadPoolExecutor
import time

app = FastAPI()
templates = Jinja2Templates(directory="templates")



class MeasurementRequest(BaseModel):
    client_name: str
    client_ip: str
    bidirectional: bool


def run_iperf3(client_ip: str, bidirectional: bool) -> str:
    bidir_flag = "--bidir" if bidirectional else ""
    command = f"iperf3 -c {client_ip} {bidir_flag} -t 3 --json"

    print(f"{time.time()}: Running {command}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr}"


# A pool executor to handle multiple client requests in parallel
executor = ThreadPoolExecutor(max_workers=10)

@app.post("/measure_client")
async def measure_client(request: MeasurementRequest):
    client_name = request.client_name
    client_ip = request.client_ip
    bidirectional = request.bidirectional
    
    # Run the iPerf3 command in a separate thread to avoid blocking the server
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, run_iperf3, client_ip, bidirectional)
    
    # Parse the JSON result
    try:
        data = json.loads(result)

        res = {
            "start_time": data["start"]["timestamp"]["time"],
            "iperf_version": data["start"]["test_start"]["protocol"],
            "num_streams": data["start"]["test_start"]["num_streams"],

            "UL": {
                "retransmits": data["end"]["sum_sent"].get("retransmits", -1),
                "Tx_bits_per_second": data["end"]["sum_sent"]["bits_per_second"],
                "Rx_bits_per_second": data["end"]["sum_received"]["bits_per_second"],
            }
        }

        if bidirectional:
            res["DL"] = {
                "retransmits": data["end"]["sum_sent_bidir_reverse"].get("retransmits", -1),
                "Tx_bits_per_second": data["end"]["sum_sent_bidir_reverse"]["bits_per_second"],
                "Rx_bits_per_second": data["end"]["sum_received_bidir_reverse"]["bits_per_second"],
            }

        return {
            "client_name": client_name,
            "client_ip": client_ip,
            "result": res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing iPerf3 result: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


