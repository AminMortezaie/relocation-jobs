from relocation_jobs.mcp.names import (
    application_cover_letter_pdf_filename,
    application_pdf_filename,
    master_pdf_filename,
)


def test_master_pdf_filename_uses_first_and_last_name():
    assert master_pdf_filename("Jane Marie Doe", "go") == "jane_doe_go.pdf"


def test_master_pdf_filename_single_name():
    assert master_pdf_filename("Madonna", "java") == "madonna_java.pdf"


def test_master_pdf_filename_empty_name_falls_back_to_resume():
    assert master_pdf_filename("", "fullstack") == "resume_fullstack.pdf"


def test_application_pdf_filename_uses_first_and_last_name():
    assert application_pdf_filename("Jane Marie Doe", "Acme Backend Ltd") == (
        "jane_doe_acme_backend_ltd.pdf"
    )


def test_application_pdf_filename_single_name():
    assert application_pdf_filename("Madonna", "Google") == "madonna_google.pdf"


def test_application_pdf_filename_empty_name_falls_back_to_resume():
    assert application_pdf_filename("", "Stripe Inc") == "resume_stripe_inc.pdf"


def test_application_cover_letter_pdf_filename():
    assert application_cover_letter_pdf_filename("Jane Marie Doe", "Acme Backend Ltd") == (
        "jane_doe_acme_backend_ltd_cover_letter.pdf"
    )
