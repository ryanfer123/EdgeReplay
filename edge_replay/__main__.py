import argparse
import json
from pathlib import Path
from .server import make_server
from .telemetry import parse_trace

parser=argparse.ArgumentParser(description='Local telemetry replay and prediction inspection')
parser.add_argument('--port',type=int,default=8766)
parser.add_argument('--database',type=Path,default=Path('edge-replay.sqlite3'))
parser.add_argument('--inspect',type=Path,help='Validate a CSV without starting a server')
parser.add_argument('--output',type=Path,help='Write an inspected recording to JSON')
args=parser.parse_args()
if args.inspect:
    try:
        result=parse_trace(args.inspect.stem,args.inspect.read_text(encoding='utf-8'))
        body=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
        if args.output:
            args.output.write_text(body+'\n',encoding='utf-8')
            print(f'Wrote {args.output}')
        else:
            print(body)
    except (OSError,ValueError) as error:
        parser.exit(2,str(error)+'\n')
else:
    server=make_server(args.port,args.database)
    print(f'EdgeReplay: http://127.0.0.1:{server.server_port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
