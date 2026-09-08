#!/usr/bin/env python3
"""
Automated tests for autonomous generation system.
Tests core functionality, error handling, and recovery.
"""

import pytest
import json
from pathlib import Path
from claude_control import (
    ClaudeController,
    ClaudeControllerException,
    ServerUnavailableException,
    GenerationStatus
)


class TestClaudeController:
    """Test suite for ClaudeController"""

    @pytest.fixture
    def controller(self):
        """Create controller instance for testing"""
        return ClaudeController()

    def test_controller_initialization(self, controller):
        """Test controller initializes correctly"""
        assert controller.base_url == "http://127.0.0.1:8188"
        assert controller.results_cache == []
        assert controller.execution_log == []

    def test_check_system_offline(self, controller):
        """Test system check when server is offline"""
        status = controller.check_system()
        assert "server_running" in status
        assert "ready" in status
        assert "message" in status

    def test_check_server(self, controller):
        """Test server availability check"""
        result = controller.check_server()
        assert isinstance(result, bool)

    def test_generate_image_simple(self, controller):
        """Test single image generation"""
        result = controller.generate_image_simple(
            "Test image",
            quality="high"
        )
        assert "status" in result
        assert "request_id" in result
        assert "output" in result or "error" in result

    def test_generate_image_series(self, controller):
        """Test multiple image generation"""
        subjects = ["Image 1", "Image 2", "Image 3"]
        results = controller.generate_image_series(subjects)
        
        assert len(results) == len(subjects)
        for result in results:
            assert "status" in result
            assert "request_id" in result

    def test_generate_video_simple(self, controller):
        """Test video generation"""
        result = controller.generate_video_simple(
            "Test video",
            length="short"
        )
        assert "status" in result
        assert "request_id" in result

    def test_orchestrate_project(self, controller):
        """Test project orchestration"""
        scenes = ["Scene 1", "Scene 2"]
        result = controller.orchestrate_content_creation(
            project_name="test_project",
            scene_descriptions=scenes
        )
        
        assert "project" in result
        assert "scenes" in result
        assert "summary" in result
        assert len(result["scenes"]) == len(scenes)

    def test_get_stats(self, controller):
        """Test statistics gathering"""
        # Generate some content first
        controller.generate_image_simple("Test")
        
        stats = controller.get_stats()
        assert "total_generations" in stats
        assert "successful" in stats
        assert "success_rate" in stats

    def test_export_results_json(self, controller):
        """Test JSON report export"""
        controller.generate_image_simple("Test")
        
        report = controller.export_results(format="json")
        assert isinstance(report, str)
        
        # Verify it's valid JSON
        parsed = json.loads(report)
        assert "generated_at" in parsed
        assert "statistics" in parsed

    def test_export_results_text(self, controller):
        """Test text report export"""
        controller.generate_image_simple("Test")
        
        report = controller.export_results(format="text")
        assert isinstance(report, str)
        assert "EVAVO Autonomous Generation Report" in report

    def test_log_action(self, controller):
        """Test action logging"""
        controller.log_action("test_action", {"detail": "value"})
        
        assert len(controller.execution_log) > 0
        log_entry = controller.execution_log[0]
        assert log_entry["action"] == "test_action"
        assert log_entry["details"]["detail"] == "value"

    def test_results_cache(self, controller):
        """Test results caching"""
        initial_size = len(controller.results_cache)
        controller.generate_image_simple("Test 1")
        controller.generate_image_simple("Test 2")
        
        assert len(controller.results_cache) == initial_size + 2

    def test_generation_quality_levels(self, controller):
        """Test different quality levels"""
        for quality in ["standard", "high", "ultra"]:
            result = controller.generate_image_simple(
                "Test image",
                quality=quality
            )
            assert result["quality"] == quality

    def test_generation_styles(self, controller):
        """Test different art styles"""
        styles = ["photorealistic", "anime", "fantasy", "oil_painting"]
        for style in styles:
            result = controller.generate_image_simple(
                "Test image",
                style=style
            )
            assert result["style"] == style

    def test_video_lengths(self, controller):
        """Test different video lengths"""
        for length in ["short", "medium", "long"]:
            result = controller.generate_video_simple(
                "Test video",
                length=length
            )
            assert result["length"] == length


class TestErrorHandling:
    """Test error handling and recovery"""

    @pytest.fixture
    def controller(self):
        """Create controller instance for testing"""
        return ClaudeController()

    def test_invalid_quality(self, controller):
        """Test handling of invalid quality parameter"""
        result = controller.generate_image_simple(
            "Test",
            quality="invalid_quality"
        )
        # Should still process (no validation error)
        assert "status" in result

    def test_empty_subject(self, controller):
        """Test handling of empty subject"""
        result = controller.generate_image_simple("")
        assert "status" in result

    def test_none_subject(self, controller):
        """Test handling of None subject"""
        try:
            result = controller.generate_image_simple(None)
            # Should handle gracefully
            assert result is not None
        except TypeError:
            # Expected behavior for None input
            pass


class TestIntegration:
    """Integration tests"""

    @pytest.fixture
    def controller(self):
        """Create controller instance for testing"""
        return ClaudeController()

    def test_full_workflow(self, controller):
        """Test complete autonomous workflow"""
        # 1. Check system
        status = controller.check_system()
        assert "ready" in status
        
        # 2. Generate images
        results = controller.generate_image_series([
            "Scene 1",
            "Scene 2"
        ])
        assert len(results) == 2
        
        # 3. Get statistics
        stats = controller.get_stats()
        assert stats["total_generations"] == 2
        
        # 4. Export results
        report = controller.export_results(format="json")
        assert isinstance(report, str)

    def test_project_workflow(self, controller):
        """Test project orchestration workflow"""
        project = controller.orchestrate_content_creation(
            project_name="test_project",
            scene_descriptions=["Scene A", "Scene B", "Scene C"]
        )
        
        assert project["project"] == "test_project"
        assert len(project["scenes"]) == 3
        assert "summary" in project


if __name__ == "__main__":
    # Run with: pytest test_autonomous.py -v
    pytest.main([__file__, "-v", "--tb=short"])
