from camoufox.async_api import AsyncCamoufox
import asyncio
from typing import List, Dict, Optional
import time
import math


class ChatGPTMetrics:
    """Class to track and calculate performance metrics"""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.worker_stats = {}
        self.question_times = []

    def start_job(self):
        self.start_time = time.time()
        print(f"Job started at {time.strftime('%H:%M:%S')}")

    def end_job(self):
        self.end_time = time.time()
        duration = self.get_total_duration()
        print(f"Job completed at {time.strftime('%H:%M:%S')}")
        print(f"Total duration: {duration:.1f} seconds ({duration / 60:.1f} minutes)")

    def get_total_duration(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0

    def add_question_result(self, result: Dict):
        worker_id = result['worker_id']
        duration = result['duration']

        if worker_id not in self.worker_stats:
            self.worker_stats[worker_id] = {
                'questions': 0,
                'total_time': 0,
                'successful': 0,
                'failed': 0
            }

        self.worker_stats[worker_id]['questions'] += 1
        self.worker_stats[worker_id]['total_time'] += duration
        self.question_times.append(duration)

        if result['response'].startswith('ERROR:'):
            self.worker_stats[worker_id]['failed'] += 1
        else:
            self.worker_stats[worker_id]['successful'] += 1

    def print_detailed_metrics(self, total_questions: int):
        if not self.start_time or not self.end_time:
            return

        total_duration = self.get_total_duration()
        successful_questions = sum(stats['successful'] for stats in self.worker_stats.values())
        failed_questions = sum(stats['failed'] for stats in self.worker_stats.values())

        print(f"\n{'=' * 50}")
        print(f"DETAILED PERFORMANCE METRICS")
        print(f"{'=' * 50}")
        print(f"Total Questions: {total_questions}")
        print(f"Successful: {successful_questions}")
        print(f"Failed: {failed_questions}")
        print(f"Success Rate: {(successful_questions / total_questions) * 100:.1f}%")
        print(f"Total Time: {total_duration:.1f}s ({total_duration / 60:.1f}m)")
        print(f"Questions/Second: {total_questions / total_duration:.2f}")
        print(f"Avg Time/Question: {sum(self.question_times) / len(self.question_times):.1f}s")
        print(f"Fastest Question: {min(self.question_times):.1f}s")
        print(f"Slowest Question: {max(self.question_times):.1f}s")

        print(f"\nWORKER BREAKDOWN:")
        for worker_id, stats in self.worker_stats.items():
            avg_time = stats['total_time'] / stats['questions'] if stats['questions'] > 0 else 0
            print(f"   Worker {worker_id}: {stats['questions']} questions, "
                  f"{stats['successful']} successful, avg {avg_time:.1f}s/question")


def calculate_optimal_workers(num_questions: int, target_seconds: int,
                              avg_time_per_question: float = 6.0,
                              max_questions_per_worker: int = 3) -> Dict:
    """
    Calculate optimal number of workers for target completion time

    Args:
        num_questions: Total questions to process
        target_seconds: Target completion time in seconds
        avg_time_per_question: Expected average time per question
        max_questions_per_worker: Max questions per worker without login

    Returns:
        Dict with worker calculation details
    """

    # Calculate based on time constraint
    questions_per_worker_time = target_seconds / avg_time_per_question
    workers_needed_time = math.ceil(num_questions / questions_per_worker_time)

    # Calculate based on login constraint (max 3 questions per worker)
    workers_needed_login = math.ceil(num_questions / max_questions_per_worker)

    # Take the higher requirement
    optimal_workers = max(workers_needed_time, workers_needed_login)

    # Calculate actual performance with optimal workers
    questions_per_worker = math.ceil(num_questions / optimal_workers)
    estimated_time = questions_per_worker * avg_time_per_question

    return {
        'optimal_workers': optimal_workers,
        'questions_per_worker': questions_per_worker,
        'estimated_time': estimated_time,
        'target_time': target_seconds,
        'will_meet_target': estimated_time <= target_seconds,
        'time_constraint_workers': workers_needed_time,
        'login_constraint_workers': workers_needed_login,
        'limiting_factor': 'login_limit' if workers_needed_login > workers_needed_time else 'time_constraint'
    }


async def worker_process_questions(questions: List[str], worker_id: int, max_questions_per_session: int = 3) -> List[
    Dict]:
    """
    Process questions with session limits to avoid login issues

    Args:
        questions: List of questions for this worker
        worker_id: Worker identification number
        max_questions_per_session: Maximum questions before needing new session
    """
    all_results = []

    # Split questions into chunks to respect session limits
    question_chunks = []
    for i in range(0, len(questions), max_questions_per_session):
        chunk = questions[i:i + max_questions_per_session]
        question_chunks.append(chunk)

    print(f"Worker {worker_id}: Processing {len(questions)} questions in {len(question_chunks)} sessions")

    for session_num, question_chunk in enumerate(question_chunks):
        print(
            f"Worker {worker_id}: Starting session {session_num + 1}/{len(question_chunks)} with {len(question_chunk)} questions")

        async with AsyncCamoufox(headless=True) as browser:
            page = await browser.new_page()

            # Initial setup for each session
            try:
                await page.goto('https://chat.openai.com/')
                await page.wait_for_load_state('networkidle')

                # Handle cookies
                cookie_selectors = ['button:has-text("Accept all")', 'button:has-text("Accept")']
                for selector in cookie_selectors:
                    try:
                        cookie_button = await page.wait_for_selector(selector, timeout=2000)
                        if cookie_button:
                            await cookie_button.click()
                            await page.wait_for_timeout(1000)
                            break
                    except:
                        continue

                await page.wait_for_timeout(3000)

                # Process questions in this session
                for q_idx, question in enumerate(question_chunk):
                    start_time = time.time()

                    try:
                        print(
                            f"Worker {worker_id}: Session {session_num + 1}, Question {q_idx + 1}/{len(question_chunk)}")

                        # Find input field
                        input_selector = None
                        selectors_to_try = [
                            'div[contenteditable="true"]',
                            '[data-placeholder="Ask anything"]',
                            'textarea[name="prompt-textarea"]',
                        ]

                        for selector in selectors_to_try:
                            try:
                                await page.wait_for_selector(selector, timeout=10000)
                                input_selector = selector
                                break
                            except:
                                continue

                        if not input_selector:
                            # If we can't find input, might need login - wait a bit
                            print(f"Worker {worker_id}: Input field not found, waiting for potential login...")
                            await page.wait_for_timeout(15000)

                            # Try once more
                            for selector in selectors_to_try:
                                try:
                                    await page.wait_for_selector(selector, timeout=5000)
                                    input_selector = selector
                                    break
                                except:
                                    continue

                        if not input_selector:
                            all_results.append({
                                'question': question,
                                'response': 'ERROR: Could not find input field - login may be required',
                                'worker_id': worker_id,
                                'duration': time.time() - start_time,
                                'session': session_num + 1
                            })
                            continue

                        # Type and send question
                        await page.click(input_selector)
                        await page.keyboard.press('Control+a')
                        await page.keyboard.type(question)
                        await page.wait_for_timeout(500)
                        await page.keyboard.press('Enter')
                        await page.wait_for_timeout(2000)

                        # Wait for response
                        response_text = ""
                        for attempt in range(60):
                            try:
                                response_elements = await page.query_selector_all(
                                    '[data-message-author-role="assistant"]')
                                if response_elements:
                                    latest_response = response_elements[-1]
                                    current_text = await latest_response.inner_text()

                                    if current_text and current_text == response_text:
                                        break
                                    response_text = current_text

                                await page.wait_for_timeout(1000)
                            except:
                                await page.wait_for_timeout(1000)

                        duration = time.time() - start_time
                        all_results.append({
                            'question': question,
                            'response': response_text or "No response received",
                            'worker_id': worker_id,
                            'duration': duration,
                            'session': session_num + 1
                        })

                        print(f"Worker {worker_id}: Completed in {duration:.1f}s")
                        await page.wait_for_timeout(1000)  # Brief pause between questions

                    except Exception as e:
                        all_results.append({
                            'question': question,
                            'response': f'ERROR: {str(e)}',
                            'worker_id': worker_id,
                            'duration': time.time() - start_time,
                            'session': session_num + 1
                        })

            except Exception as e:
                # If entire session fails
                for question in question_chunk:
                    all_results.append({
                        'question': question,
                        'response': f'ERROR: Session failed - {str(e)}',
                        'worker_id': worker_id,
                        'duration': 0,
                        'session': session_num + 1
                    })

        # Brief pause between sessions
        if session_num < len(question_chunks) - 1:
            print(f"Worker {worker_id}: Pausing between sessions...")
            await asyncio.sleep(2)

    return all_results


async def scrape_chatgpt_auto_workers(questions: List[str], target_seconds: int,
                                      avg_time_per_question: float = 6.0) -> Dict:
    """
    Automatically determine optimal workers and scrape questions to meet target time

    Args:
        questions: List of questions to process
        target_seconds: Target completion time in seconds
        avg_time_per_question: Expected average time per question

    Returns:
        Dict with results and metrics
    """

    # Calculate optimal workers
    worker_calc = calculate_optimal_workers(
        len(questions),
        target_seconds,
        avg_time_per_question
    )

    print(f"TARGET: Complete {len(questions)} questions in {target_seconds} seconds")
    print(f"WORKER CALCULATION:")
    print(f"   • Time constraint needs: {worker_calc['time_constraint_workers']} workers")
    print(f"   • Login constraint needs: {worker_calc['login_constraint_workers']} workers")
    print(f"   • Limiting factor: {worker_calc['limiting_factor']}")
    print(f"   • Optimal workers: {worker_calc['optimal_workers']}")
    print(f"   • Questions per worker: {worker_calc['questions_per_worker']}")
    print(f"   • Estimated time: {worker_calc['estimated_time']:.1f} seconds")
    print(f"   • Will meet target: {'YES' if worker_calc['will_meet_target'] else 'NO'}")

    # Run the scraping with calculated workers
    results = await scrape_chatgpt_parallel(questions, worker_calc['optimal_workers'])

    return {
        'results': results,
        'worker_calculation': worker_calc,
        'actual_duration': results[0]['metrics'].get_total_duration() if results else 0
    }


async def scrape_chatgpt_parallel(questions: List[str], num_workers: int = 5) -> List[Dict]:
    """
    Enhanced parallel scraper with session limits and detailed metrics
    """

    if len(questions) == 0:
        return []

    # Initialize metrics
    metrics = ChatGPTMetrics()
    metrics.start_job()

    # Don't use more workers than questions
    num_workers = min(num_workers, len(questions))

    print(f"SETUP: {num_workers} workers, {len(questions)} questions")
    print(f"SESSION LIMIT: Max 3 questions per browser session (to avoid login issues)")

    # Split questions among workers
    questions_per_worker = len(questions) // num_workers
    question_batches = []

    for i in range(num_workers):
        start_idx = i * questions_per_worker
        if i == num_workers - 1:
            end_idx = len(questions)
        else:
            end_idx = (i + 1) * questions_per_worker

        question_batches.append(questions[start_idx:end_idx])

    print(f"DISTRIBUTION: {[len(batch) for batch in question_batches]} questions per worker")

    # Run workers in parallel
    tasks = [
        worker_process_questions(batch, worker_id, max_questions_per_session=3)
        for worker_id, batch in enumerate(question_batches)
    ]

    batch_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Combine results and calculate metrics
    all_results = []
    for worker_results in batch_results:
        if isinstance(worker_results, Exception):
            print(f"Worker failed: {worker_results}")
        else:
            all_results.extend(worker_results)
            # Add to metrics
            for result in worker_results:
                metrics.add_question_result(result)

    metrics.end_job()
    metrics.print_detailed_metrics(len(questions))

    # Add metrics to results
    for result in all_results:
        result['metrics'] = metrics

    return all_results


# Simple usage functions
async def main():
    questions = [
        "How do I fix a Python error: ModuleNotFoundError?",
        "Can you write a SQL query to find duplicate records in a table?",
        "How do I optimize a PostgreSQL database for faster queries?",
        "What's the difference between multithreading and multiprocessing in Python?",
        "Can you explain the difference between REST API and GraphQL?",
        "How do I deploy a .NET application in Docker?",
        "Can you write a Python script to scrape Amazon product titles?",
        "How do I set up CI/CD in GitHub Actions for a C# project?",
        "Can you help me debug a Selenium script that fails to click a button?",
        "How do I schedule a cron job to run daily at 5 PM?"
    ]


    print("\n=== MANUAL WORKER SETTING ===")
    results = await scrape_chatgpt_parallel(questions, num_workers=5)

    # Save results
    import json
    with open('chatgpt_results.json', 'w', encoding='utf-8') as f:
        # Remove metrics object for JSON serialization
        json_results = []
        for r in results:
            json_result = r.copy()
            if 'metrics' in json_result:
                del json_result['metrics']
            json_results.append(json_result)
        json.dump(json_results, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    asyncio.run(main())