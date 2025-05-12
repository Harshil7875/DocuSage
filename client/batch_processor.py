# client/batch_processor.py

#!/usr/bin/env python3
"""
DocuSage Batch Processor
Process multiple documents at once using the batch endpoint.
"""

import requests
import sys
import os
import argparse
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_colored(text, color):
    print(f"{color}{text}{Colors.ENDC}")

def process_directory(directory, server, port, length='standard', language='en', 
                     extensions=['.txt', '.pdf'], output_dir=None):
    """Process all documents in a directory"""
    
    # Find all matching files
    files_to_process = []
    for ext in extensions:
        files_to_process.extend(Path(directory).glob(f'**/*{ext}'))
    
    if not files_to_process:
        print_colored(f"No files found with extensions: {extensions}", Colors.YELLOW)
        return
    
    print_colored(f"Found {len(files_to_process)} files to process", Colors.BLUE)
    
    # Create output directory if specified
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    url = f"http://{server}:{port}/batch_summarize"
    
    # Process files in batches of 5
    batch_size = 5
    total_processed = 0
    failed_files = []
    
    for i in range(0, len(files_to_process), batch_size):
        batch = files_to_process[i:i+batch_size]
        print_colored(f"\nProcessing batch {i//batch_size + 1} of {(len(files_to_process)-1)//batch_size + 1}", Colors.BLUE)
        
        files = []
        for file_path in batch:
            with open(file_path, 'rb') as f:
                files.append(('files', (file_path.name, f.read(), 'application/octet-stream')))
        
        try:
            response = requests.post(url, files=files, timeout=300)
            response.raise_for_status()
            results = response.json()['results']
            
            for idx, result in enumerate(results):
                file_path = batch[idx]
                if result['success']:
                    print_colored(f"✓ {file_path.name}", Colors.GREEN)
                    
                    # Save summary
                    if output_dir:
                        output_file = Path(output_dir) / f"{file_path.stem}_summary.txt"
                        with open(output_file, 'w') as f:
                            f.write(result['summary'])
                    
                    total_processed += 1
                else:
                    print_colored(f"✗ {file_path.name}: {result['error']}", Colors.RED)
                    failed_files.append(file_path)
                    
        except Exception as e:
            print_colored(f"Batch failed: {e}", Colors.RED)
            failed_files.extend(batch)
    
    # Summary
    print_colored(f"\n{'='*50}", Colors.HEADER)
    print_colored(f"Batch processing complete!", Colors.GREEN)
    print_colored(f"Successfully processed: {total_processed}", Colors.GREEN)
    print_colored(f"Failed: {len(failed_files)}", Colors.RED if failed_files else Colors.GREEN)
    
    if failed_files:
        print_colored("\nFailed files:", Colors.YELLOW)
        for f in failed_files:
            print(f"  - {f}")

def main():
    parser = argparse.ArgumentParser(description='DocuSage Batch Processor')
    parser.add_argument('server', help='Server IP address')
    parser.add_argument('directory', help='Directory containing documents')
    parser.add_argument('--port', '-p', default='8000', help='Server port')
    parser.add_argument('--length', '-l', choices=['brief', 'standard', 'detailed'], 
                       default='standard', help='Summary length')
    parser.add_argument('--language', '-L', choices=['en', 'es', 'fr', 'de', 'ja', 'zh'], 
                       default='en', help='Summary language')
    parser.add_argument('--extensions', '-e', nargs='+', default=['.txt', '.pdf'],
                       help='File extensions to process')
    parser.add_argument('--output', '-o', help='Output directory for summaries')
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.directory):
        print_colored(f"Error: {args.directory} is not a directory", Colors.RED)
        sys.exit(1)
    
    process_directory(
        args.directory,
        args.server,
        args.port,
        args.length,
        args.language,
        args.extensions,
        args.output
    )

if __name__ == "__main__":
    main()