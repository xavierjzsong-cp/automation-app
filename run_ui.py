"""Application entry point for Template Automation Tool."""

from src.services.template_generation_service import TemplateGenerationService


def main() -> None:
    """Run the desktop application.

    The real CustomTkinter UI will be added in a later step. For now this
    entry point proves the application package can be imported and started.
    """
    TemplateGenerationService()
    print("Template Automation Tool baseline is ready.")


if __name__ == "__main__":
    main()
