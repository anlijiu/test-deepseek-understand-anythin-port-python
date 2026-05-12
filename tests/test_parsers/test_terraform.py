"""Terraform parser tests — ported from terraform-parser.test.ts."""

from __future__ import annotations

from understand_anything.plugins.parsers.terraform import TerraformParser


class TestTerraformParser:
    """Tests for TerraformParser."""

    def test_language_ids(self):
        """Parser reports correct language IDs."""
        parser = TerraformParser()
        assert parser.name == "terraform-parser"
        assert parser.languages == ["terraform"]

    def test_extracts_resource_blocks(self):
        """Extract resource blocks."""
        content = """resource "aws_instance" "web" {
    ami           = "ami-12345"
    instance_type = "t2.micro"
}

resource "aws_s3_bucket" "assets" {
    bucket = "my-assets-bucket"
}
"""
        parser = TerraformParser()
        result = parser.analyze_file("main.tf", content)

        assert len(result.resources) == 2
        assert result.resources[0].name == "aws_instance.web"
        assert result.resources[0].kind == "aws_instance"
        assert result.resources[1].name == "aws_s3_bucket.assets"
        assert result.resources[1].kind == "aws_s3_bucket"

    def test_extracts_data_blocks(self):
        """Extract data source blocks."""
        content = """data "aws_ami" "ubuntu" {
    most_recent = true
    filter {
        name   = "name"
        values = ["ubuntu/images/*"]
    }
}
"""
        parser = TerraformParser()
        result = parser.analyze_file("data.tf", content)

        assert len(result.resources) == 1
        assert result.resources[0].name == "data.aws_ami.ubuntu"
        assert result.resources[0].kind == "data.aws_ami"

    def test_extracts_module_blocks(self):
        """Extract module blocks."""
        content = """module "vpc" {
    source = "terraform-aws-modules/vpc/aws"
    version = "5.0.0"
}

module "webserver" {
    source = "./modules/webserver"
}
"""
        parser = TerraformParser()
        result = parser.analyze_file("main.tf", content)

        modules = [r for r in result.resources if r.kind == "module"]
        assert len(modules) == 2
        assert modules[0].name == "module.vpc"
        assert modules[1].name == "module.webserver"

    def test_extracts_variable_and_output_definitions(self):
        """Extract variable and output blocks as definitions."""
        content = """variable "region" {
    description = "AWS region"
    type        = string
    default     = "us-east-1"
}

variable "instance_count" {
    type    = number
    default = 2
}

output "instance_ip" {
    value = aws_instance.web.public_ip
}
"""
        parser = TerraformParser()
        result = parser.analyze_file("vars.tf", content)

        variables = [d for d in result.definitions if d.kind == "variable"]
        outputs = [d for d in result.definitions if d.kind == "output"]
        assert len(variables) == 2
        assert variables[0].name == "region"
        assert variables[1].name == "instance_count"
        assert len(outputs) == 1
        assert outputs[0].name == "instance_ip"

    def test_resource_line_ranges_are_correct(self):
        """Resource line ranges cover the full block."""
        content = """resource "aws_instance" "test" {
    ami = "ami-123"
    instance_type = "t2.micro"
}
"""
        parser = TerraformParser()
        result = parser.analyze_file("test.tf", content)

        assert len(result.resources) == 1
        assert result.resources[0].line_range[0] == 1
        assert result.resources[0].line_range[1] >= 3

    def test_empty_fields_are_empty_lists(self):
        """Code-only fields are empty."""
        parser = TerraformParser()
        result = parser.analyze_file("test.tf", 'resource "null" "test" {}')
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.exports == []
