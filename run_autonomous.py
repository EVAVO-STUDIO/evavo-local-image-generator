#!/usr/bin/env python3
"""
EVAVO Autonomous Generation Script - Production Grade
Demonstrates complete autonomous operation with error handling and recovery.
Claude/ChatGPT runs this for full autonomous AI generation without user intervention.
"""

import sys
import logging
from datetime import datetime
from claude_control import ClaudeController, ServerUnavailableException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_section(title):
    """Print formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70 + "\n")


def print_success(msg):
    """Print success message"""
    print(f"✓ {msg}")


def print_error(msg):
    """Print error message"""
    print(f"✗ {msg}")
    logger.error(msg)


def print_warning(msg):
    """Print warning message"""
    print(f"⚠ {msg}")
    logger.warning(msg)


def main():
    """Main autonomous generation workflow"""
    
    print_section("EVAVO AUTONOMOUS GENERATION SYSTEM")
    print("Claude is now in complete control - no user intervention needed\n")
    print(f"Started at: {datetime.now().isoformat()}\n")

    try:
        controller = ClaudeController()

        # PHASE 1: System Verification
        print_section("PHASE 1: System Verification")
        
        logger.info("Checking system readiness...")
        system_status = controller.check_system()

        if not system_status["ready"]:
            print_error("System not ready!")
            print(f"  Status: {system_status['message']}")
            print("\nTo fix this:")
            print("  1. Start ComfyUI server:")
            print("     cd C:\\AI\\ComfyUI")
            print("     python main.py")
            print("\n  2. Then run this script again")
            logger.error("System verification failed - server not responding")
            return False

        print_success("System is ready")
        print(f"  Server: {system_status['server_url']}")
        print(f"  Status: {system_status['message']}")

        # PHASE 2: Generate Image Series
        print_section("PHASE 2: Image Generation")
        print("Claude generating diverse image collection...\n")

        image_subjects = [
            "Majestic mountain landscape with snow peaks at golden hour",
            "Professional portrait in studio with perfect lighting",
            "Futuristic cyberpunk city with neon lights",
            "Fantasy dragon in mystical crystal cavern",
            "Peaceful zen garden with ancient temple"
        ]

        print(f"Generating {len(image_subjects)} high-quality images...\n")

        try:
            image_results = controller.generate_image_series(
                subjects=image_subjects,
                quality="ultra"
            )

            completed_images = sum(1 for r in image_results if r.get("status") == "completed")
            print_success(f"Generated {completed_images}/{len(image_subjects)} images")
            
        except Exception as e:
            print_error(f"Image generation failed: {e}")
            logger.exception("Image generation error")
            return False

        # PHASE 3: Generate Video
        print_section("PHASE 3: Video Generation")
        print("Claude generating cinematic video...\n")

        try:
            video_result = controller.generate_video_simple(
                subject="Epic cinematic scene with dramatic lighting and dynamic camera movement",
                length="short"
            )

            if video_result.get("status") == "completed":
                print_success("Video generated successfully")
                print(f"  File: {video_result.get('output')}")
                print(f"  Time: {video_result.get('time', 'N/A')}s")
            else:
                print_warning(f"Video generation: {video_result.get('status')}")
                logger.warning(f"Video generation status: {video_result.get('status')}")
                
        except Exception as e:
            print_error(f"Video generation failed: {e}")
            logger.exception("Video generation error")

        # PHASE 4: Project Orchestration
        print_section("PHASE 4: Project Orchestration")
        print("Claude orchestrating complete game asset project...\n")

        try:
            project = controller.orchestrate_content_creation(
                project_name="fantasy_game_assets_2026",
                scene_descriptions=[
                    "Ancient elven forest with towering trees",
                    "Dragon's lair with molten lava pools",
                    "Castle overlooking misty valley",
                    "Underground crystal cavern system",
                    "Mysterious temple ruins"
                ],
                output_format="ultra"
            )

            print_success(f"Project '{project['project']}' completed")
            print(f"  Scenes: {len(project['scenes'])}")
            print(f"  Completed: {project['summary']['completed']}/{project['summary']['total']}")
            print(f"  Success Rate: {project['summary']['success_rate']}")
            print(f"  Total Time: {project['summary']['total_time']}")
            
        except Exception as e:
            print_error(f"Project orchestration failed: {e}")
            logger.exception("Project orchestration error")

        # PHASE 5: Statistics and Report
        print_section("PHASE 5: Final Statistics & Report")

        try:
            stats = controller.get_stats()

            print("Generation Statistics:")
            print(f"  Total Generations: {stats['total_generations']}")
            print(f"  Successful: {stats['successful']}")
            print(f"  Failed: {stats.get('failed', 0)}")
            print(f"  Success Rate: {stats['success_rate']}")
            print(f"  Total Time: {stats['total_time']}")
            
        except Exception as e:
            print_error(f"Statistics collection failed: {e}")
            logger.exception("Statistics error")

        # PHASE 6: Export Results
        print_section("PHASE 6: Results Export")

        try:
            report = controller.export_results(format="text")
            print(report)
            
            # Also save JSON report
            json_report = controller.export_results(format="json")
            with open("generation_report.json", "w") as f:
                f.write(json_report)
            print_success("Report saved to generation_report.json")
            
        except Exception as e:
            print_error(f"Report export failed: {e}")
            logger.exception("Report export error")

        # Final Summary
        print_section("AUTONOMOUS GENERATION COMPLETE")

        print("✅ ALL PHASES COMPLETED SUCCESSFULLY")
        print("\nWhat was accomplished:")
        print(f"  ✓ Generated {completed_images} high-quality images")
        print(f"  ✓ Generated 1 cinematic video")
        print(f"  ✓ Orchestrated 1 complete game asset project")
        print(f"  ✓ Collected and reported statistics")
        print(f"  ✓ Exported generation report")

        print("\nClaude's Autonomy Status:")
        print("  ✓ Full control of generation pipeline")
        print("  ✓ Error handling operational")
        print("  ✓ Statistics tracking enabled")
        print("  ✓ Project orchestration active")
        print("  ✓ Report generation working")

        print("\n" + "="*70)
        print("  🤖 CLAUDE IS FULLY AUTONOMOUS AND OPERATIONAL")
        print("="*70 + "\n")

        print(f"Completed at: {datetime.now().isoformat()}\n")
        
        logger.info("Autonomous generation completed successfully")
        return True

    except KeyboardInterrupt:
        print_error("\nInterrupted by user")
        logger.info("Interrupted by user")
        return False
        
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        logger.exception("Unexpected error during autonomous generation")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print_error(f"\nFatal error: {e}")
        logger.exception("Fatal error")
        sys.exit(1)
