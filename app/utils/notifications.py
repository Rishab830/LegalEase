from flask import current_app
from flask_mail import Message
from app.models import Notification, User
from bson import ObjectId

def add_notification(user_id, n_type, message, link=None, send_email=False, email_subject=None):
    """
    Create an in-app notification and optionally send an email.
    """
    # Create DB record
    Notification.create(user_id, n_type, message, link)
    
    # Send email if requested
    # if send_email:
    #     # Avoid circular import
    #     from app.extensions import mail
    #     
    #     user_data = User.get(user_id)
    #     if user_data and user_data.email:
    #         try:
    #             msg = Message(
    #                 subject=email_subject or f"LegalEase Notification: {n_type.capitalize()}",
    #                 recipients=[user_data.email],
    #                 body=f"Hello {user_data.username or 'User'},\n\n{message}\n\nYou can view the details here: {link if link else 'N/A'}\n\nBest regards,\nLegalEase Team"
    #             )
    #             mail.send(msg)
    #         except Exception as e:
    #             current_app.logger.error(f"Failed to send notification email: {str(e)}")

def notify_processing_complete(user_id, doc_id, filename):
    """Notify user that document processing is finished."""
    message = f"Your document '{filename}' has been processed successfully."
    # Build URL manually to avoid context issues in background threads
    link = f"/document/{doc_id}/analysis"
    add_notification(user_id, 'success', message, link)

def notify_high_risk_detected(user_id, doc_id, filename, high_risk_clauses):
    """Notify user about high-risk clauses and send email."""
    clause_names = ", ".join([c['name'] for c in high_risk_clauses])
    message = f"High-risk clauses detected in '{filename}': {clause_names}. Please review the analysis immediately."
    # Build URL manually to avoid context issues in background threads
    link = f"/document/{doc_id}/analysis"
    
    add_notification(
        user_id=user_id,
        n_type='danger',
        message=message,
        link=link,
        send_email=True,
        email_subject="CRITICAL: High Risk Clauses Detected"
    )
