# Codebase Map

## Summary

- **Modules**: 85
- **Classes**: 123
- **Functions/Methods**: 556
- **Internal imports**: 56 modules with cross-imports
- **Call sites**: 4969

## Module Dependencies

| Module | Depends On |
|--------|-----------|
| `src.api.admin.backup_manager` | `src.config` |
| `src.api.admin.document_manager` | `src.config`, `src.document_processing.description_generator` |
| `src.api.api` | `src.api.admin.audit_logger`, `src.api.admin.backup_manager`, `src.api.admin.document_manager`, `src.api.auth`, `src.api.models`, `src.api.routes.admin`, `src.api.routes.analytics`, `src.api.routes.auth`, `src.api.routes.conversations`, `src.api.routes.feedback`, `src.api.routes.onboarding`, `src.api.routes.query`, `src.api.routes.team`, `src.api.routes.tenant_admin`, `src.config`, `src.document_processing.document_processor`, `src.document_processing.kb_manager`, `src.email.conversation_manager`, `src.email.email_sender`, `src.platform.bootstrap`, `src.platform.component_factory`, `src.platform.component_resolver`, `src.rag.example_questions`, `src.rag.query_handler` |
| `src.api.auth` | `src.api.auth.dependencies`, `src.api.auth.otp_manager`, `src.api.auth.session_manager` |
| `src.api.auth.otp_manager` | `src.api.models` |
| `src.api.auth.session_manager` | `src.config` |
| `src.api.routes.admin` | `src.api.admin.document_manager`, `src.api.models`, `src.api.routes.helpers`, `src.document_processing.description_generator`, `src.rag.example_questions`, `src.rag.rag_engine` |
| `src.api.routes.analytics` | `src.api.models`, `src.api.routes.helpers`, `src.email.db_models`, `src.rag.topic_clustering` |
| `src.api.routes.auth` | `src.api.auth.otp_email`, `src.api.models`, `src.platform.models` |
| `src.api.routes.conversations` | `src.api.models`, `src.api.routes.helpers`, `src.email.db_models` |
| `src.api.routes.feedback` | `src.api.models`, `src.api.routes.helpers`, `src.email.conversation_manager`, `src.email.db_models`, `src.email.email_sender` |
| `src.api.routes.onboarding` | `src.api.models`, `src.email.email_sender`, `src.platform.models`, `src.platform.provisioning`, `src.platform.storage` |
| `src.api.routes.query` | `src.api.models`, `src.api.routes.helpers`, `src.email.conversation_manager`, `src.email.db_models` |
| `src.api.routes.team` | `src.api.models`, `src.email.email_sender`, `src.platform.models` |
| `src.api.routes.tenant_admin` | `src.api.models`, `src.email.email_sender`, `src.platform.models`, `src.platform.provisioning` |
| `src.cli.commands.backup` | `src.api.admin.backup_manager`, `src.cli.utils` |
| `src.cli.commands.db` | `src.cli.utils`, `src.config`, `src.email.db_manager`, `src.email.db_models`, `src.email.message_tracker` |
| `src.cli.commands.kb` | `src.cli.utils`, `src.config`, `src.document_processing.description_generator`, `src.document_processing.document_processor`, `src.document_processing.kb_manager`, `src.rag.query_handler` |
| `src.cli.main` | `src.cli.commands`, `src.cli.utils`, `src.config` |
| `src.document_processing.description_generator` | `src.config`, `src.email.db_manager`, `src.email.db_models` |
| `src.document_processing.document_processor` | `src.config`, `src.document_processing.enhancement_processor`, `src.document_processing.web_crawler` |
| `src.document_processing.enhancement_processor` | `src.config` |
| `src.document_processing.file_watcher` | `src.config`, `src.document_processing.document_processor`, `src.document_processing.kb_manager` |
| `src.document_processing.kb_manager` | `src.config` |
| `src.document_processing.web_crawler` | `src.config` |
| `src.email` | `src.email.attachment_handler`, `src.email.email_client`, `src.email.email_parser`, `src.email.email_processor`, `src.email.email_sender`, `src.email.message_tracker` |
| `src.email.attachment_handler` | `src.config` |
| `src.email.conversation_manager` | `src.email.db_manager`, `src.email.db_models` |
| `src.email.db_manager` | `src.config`, `src.email.db_models` |
| `src.email.email_client` | `src.config` |
| `src.email.email_parser` | `src.config` |
| `src.email.email_processor` | `src.config`, `src.document_processing.document_processor`, `src.document_processing.kb_manager`, `src.email.attachment_handler`, `src.email.conversation_manager`, `src.email.email_client`, `src.email.email_parser`, `src.email.email_sender`, `src.email.message_tracker`, `src.email.tenant_email_router`, `src.rag.query_handler` |
| `src.email.email_sender` | `src.config`, `src.platform.db_manager`, `src.platform.models` |
| `src.email.email_service` | `src.config`, `src.email.email_processor`, `src.email.tenant_email_router`, `src.platform.bootstrap`, `src.platform.component_factory` |
| `src.email.message_tracker` | `src.email.db_manager`, `src.email.db_models` |
| `src.email.tenant_email_router` | `src.platform.component_factory`, `src.platform.db_manager`, `src.platform.models`, `src.platform.tenant_context` |
| `src.platform.bootstrap` | `src.config`, `src.platform.db_manager`, `src.platform.encryption`, `src.platform.models`, `src.platform.provisioning`, `src.platform.storage` |
| `src.platform.component_factory` | `src.document_processing.document_processor`, `src.document_processing.kb_manager`, `src.email.conversation_manager`, `src.platform.db_session_adapter`, `src.platform.models`, `src.platform.tenant_context`, `src.rag.query_handler`, `src.rag.rag_engine` |
| `src.platform.component_resolver` | `src.platform.component_factory` |
| `src.platform.db_manager` | `src.config`, `src.email.db_models`, `src.platform.models` |
| `src.platform.encryption` | `src.config`, `src.platform.models` |
| `src.platform.provisioning` | `src.config`, `src.platform.db_manager`, `src.platform.encryption`, `src.platform.models`, `src.platform.storage` |
| `src.platform.storage` | `src.config` |
| `src.platform.tenant_context` | `src.config`, `src.platform.storage` |
| `src.platform_admin.app` | `src.api.auth.otp_manager`, `src.config`, `src.email.email_sender`, `src.platform.bootstrap`, `src.platform_admin.routes.auth`, `src.platform_admin.routes.health`, `src.platform_admin.routes.tenants` |
| `src.platform_admin.routes.auth` | `src.api.auth.otp_email`, `src.platform_admin.models` |
| `src.platform_admin.routes.health` | `src.platform.models`, `src.platform_admin.models`, `src.platform_admin.routes.auth` |
| `src.platform_admin.routes.tenants` | `src.platform.models`, `src.platform_admin.models`, `src.platform_admin.routes.auth` |
| `src.rag.example_questions` | `src.rag.rag_engine` |
| `src.rag.query_handler` | `src.rag.query_optimizer`, `src.rag.rag_engine`, `src.rag.tools` |
| `src.rag.query_optimizer` | `src.config` |
| `src.rag.rag_engine` | `src.config`, `src.document_processing.kb_manager`, `src.rag.tools` |
| `src.rag.tools.database_tools` | `src.email.conversation_manager` |
| `src.rag.tools.rag_tools` | `src.config`, `src.document_processing.kb_manager` |
| `src.rag.tools.team_tools` | `src.config`, `src.email.email_sender`, `src.platform.models` |
| `src.rag.tools.web_search_tools` | `src.config` |

## Classes

| Class | Module | Bases | Methods |
|-------|--------|-------|---------|
| `src.api.admin.audit_logger.AdminAuditLogger` | `src.api.admin.audit_logger` | - | 3 |
| `src.api.admin.backup_manager.BackupManager` | `src.api.admin.backup_manager` | - | 8 |
| `src.api.admin.document_manager.DocumentManager` | `src.api.admin.document_manager` | - | 7 |
| `src.api.auth.otp_manager.OTPManager` | `src.api.auth.otp_manager` | - | 4 |
| `src.api.auth.session_manager.Session` | `src.api.auth.session_manager` | - | 4 |
| `src.api.auth.session_manager.SessionManager` | `src.api.auth.session_manager` | - | 5 |
| `src.api.models.AdminActionResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.AuthResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.AuthStatusResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.ConversationListItem` | `src.api.models` | BaseModel | 0 |
| `src.api.models.ConversationMessagesResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.ConversationSearchResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.ConversationsResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.CrawlRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.CrawledUrlResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.CreateTenantRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.CreateTenantResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.DocumentDeleteRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.DocumentListResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.FeedbackAnalyticsResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.FeedbackRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.FeedbackResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.HistoryResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.JoinRequestActionResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.JoinTenantRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.JoinTenantResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.OTPEntry` | `src.api.models` | - | 3 |
| `src.api.models.OTPRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.OTPVerifyRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.QueryRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.QueryResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.SlugCheckResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.StatsResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.TeamMemberRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.TeamMemberResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.TenantSelectRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.TenantSettingsRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.TopicClusteringResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.UsageAnalyticsResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.UserQueriesResponse` | `src.api.models` | BaseModel | 0 |
| `src.api.models.ValidateCodeRequest` | `src.api.models` | BaseModel | 0 |
| `src.api.models.ValidateCodeResponse` | `src.api.models` | BaseModel | 0 |
| `src.config.Settings` | `src.config` | BaseSettings | 8 |
| `src.document_processing.description_generator.DescriptionGenerator` | `src.document_processing.description_generator` | - | 6 |
| `src.document_processing.document_processor.DocumentProcessor` | `src.document_processing.document_processor` | - | 11 |
| `src.document_processing.enhancement_processor.EnhancementProcessor` | `src.document_processing.enhancement_processor` | - | 5 |
| `src.document_processing.file_watcher.DocumentEventHandler` | `src.document_processing.file_watcher` | FileSystemEventHandler | 5 |
| `src.document_processing.file_watcher.FileWatcher` | `src.document_processing.file_watcher` | - | 5 |
| `src.document_processing.kb_manager.KnowledgeBaseManager` | `src.document_processing.kb_manager` | - | 17 |
| `src.document_processing.web_crawler.WebCrawler` | `src.document_processing.web_crawler` | - | 8 |
| `src.email.attachment_handler.AttachmentError` | `src.email.attachment_handler` | Exception | 0 |
| `src.email.attachment_handler.AttachmentHandler` | `src.email.attachment_handler` | - | 10 |
| `src.email.attachment_handler.AttachmentInfo` | `src.email.attachment_handler` | - | 2 |
| `src.email.attachment_handler.FileSizeError` | `src.email.attachment_handler` | AttachmentError | 0 |
| `src.email.attachment_handler.FileTypeError` | `src.email.attachment_handler` | AttachmentError | 0 |
| `src.email.conversation_manager.ConversationManager` | `src.email.conversation_manager` | - | 17 |
| `src.email.db_manager.DatabaseManager` | `src.email.db_manager` | - | 8 |
| `src.email.db_models.ChannelType` | `src.email.db_models` | enum.Enum | 0 |
| `src.email.db_models.Conversation` | `src.email.db_models` | Base | 3 |
| `src.email.db_models.ConversationMessage` | `src.email.db_models` | Base | 3 |
| `src.email.db_models.DocumentDescription` | `src.email.db_models` | Base | 3 |
| `src.email.db_models.MessageType` | `src.email.db_models` | enum.Enum | 0 |
| `src.email.db_models.ProcessedMessage` | `src.email.db_models` | Base | 3 |
| `src.email.db_models.ProcessingStats` | `src.email.db_models` | Base | 3 |
| `src.email.db_models.ResponseFeedback` | `src.email.db_models` | Base | 3 |
| `src.email.email_client.EmailAuthenticationError` | `src.email.email_client` | EmailClientError | 0 |
| `src.email.email_client.EmailClient` | `src.email.email_client` | - | 13 |
| `src.email.email_client.EmailClientError` | `src.email.email_client` | Exception | 0 |
| `src.email.email_client.EmailConnectionError` | `src.email.email_client` | EmailClientError | 0 |
| `src.email.email_parser.EmailAddress` | `src.email.email_parser` | BaseModel | 2 |
| `src.email.email_parser.EmailMessage` | `src.email.email_parser` | BaseModel | 4 |
| `src.email.email_parser.EmailParser` | `src.email.email_parser` | - | 12 |
| `src.email.email_processor.EmailProcessor` | `src.email.email_processor` | - | 11 |
| `src.email.email_processor.ProcessingResult` | `src.email.email_processor` | - | 0 |
| `src.email.email_sender.EmailSender` | `src.email.email_sender` | - | 4 |
| `src.email.email_service.EmailService` | `src.email.email_service` | - | 9 |
| `src.email.message_tracker.MessageTracker` | `src.email.message_tracker` | - | 6 |
| `src.email.tenant_email_router.TenantEmailRouter` | `src.email.tenant_email_router` | - | 5 |
| `src.platform.bootstrap.PlatformInfra` | `src.platform.bootstrap` | - | 0 |
| `src.platform.component_factory.TenantComponentFactory` | `src.platform.component_factory` | - | 6 |
| `src.platform.component_factory.TenantComponents` | `src.platform.component_factory` | - | 0 |
| `src.platform.component_factory._CacheEntry` | `src.platform.component_factory` | - | 1 |
| `src.platform.component_resolver.ComponentResolver` | `src.platform.component_resolver` | - | 2 |
| `src.platform.db_manager.TenantDBManager` | `src.platform.db_manager` | - | 19 |
| `src.platform.db_manager._TenantEngineEntry` | `src.platform.db_manager` | - | 1 |
| `src.platform.db_session_adapter.TenantDBSessionAdapter` | `src.platform.db_session_adapter` | - | 2 |
| `src.platform.encryption.DatabaseKeyManager` | `src.platform.encryption` | KeyManager | 10 |
| `src.platform.encryption.KeyManager` | `src.platform.encryption` | ABC | 4 |
| `src.platform.encryption.TenantEncryptor` | `src.platform.encryption` | - | 3 |
| `src.platform.models.JoinRequest` | `src.platform.models` | PlatformBase | 2 |
| `src.platform.models.JoinRequestStatus` | `src.platform.models` | enum.Enum | 0 |
| `src.platform.models.Tenant` | `src.platform.models` | PlatformBase | 3 |
| `src.platform.models.TenantEncryptionKey` | `src.platform.models` | PlatformBase | 1 |
| `src.platform.models.TenantStatus` | `src.platform.models` | enum.Enum | 0 |
| `src.platform.models.TenantUser` | `src.platform.models` | PlatformBase | 2 |
| `src.platform.models.TenantUserRole` | `src.platform.models` | enum.Enum | 0 |
| `src.platform.provisioning.ProvisioningError` | `src.platform.provisioning` | Exception | 0 |
| `src.platform.provisioning.TenantProvisioner` | `src.platform.provisioning` | - | 10 |
| `src.platform.storage.LocalStorageBackend` | `src.platform.storage` | StorageBackend | 11 |
| `src.platform.storage.S3StorageBackend` | `src.platform.storage` | StorageBackend | 9 |
| `src.platform.storage.StorageBackend` | `src.platform.storage` | ABC | 7 |
| `src.platform.tenant_context.TenantContext` | `src.platform.tenant_context` | - | 2 |
| `src.platform_admin.models.AdminAuthResponse` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.AdminAuthStatus` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.AdminOTPRequest` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.AdminOTPVerifyRequest` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.PlatformHealth` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.TenantCreateRequest` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.TenantDetail` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.TenantStats` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.TenantSummary` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.TenantUserRequest` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.models.TenantUserResponse` | `src.platform_admin.models` | BaseModel | 0 |
| `src.platform_admin.routes.auth.AdminSession` | `src.platform_admin.routes.auth` | - | 0 |
| `src.platform_admin.routes.auth.AdminSessionManager` | `src.platform_admin.routes.auth` | - | 4 |
| `src.rag.query_handler.QueryHandler` | `src.rag.query_handler` | - | 3 |
| `src.rag.query_optimizer.QueryOptimizer` | `src.rag.query_optimizer` | - | 5 |
| `src.rag.rag_engine.RAGEngine` | `src.rag.rag_engine` | - | 4 |
| `src.rag.tools.base.ParameterType` | `src.rag.tools.base` | str, Enum | 0 |
| `src.rag.tools.base.Tool` | `src.rag.tools.base` | - | 2 |
| `src.rag.tools.base.ToolParameter` | `src.rag.tools.base` | - | 0 |
| `src.rag.tools.base.ToolRegistry` | `src.rag.tools.base` | - | 5 |
| `src.rag.tools.tool_executor.ToolExecutor` | `src.rag.tools.tool_executor` | - | 4 |

## Potential Orphans (not called from other modules)

*These functions/methods are not called from outside their module. Some may be entry points, route handlers, or legitimately module-internal.*

| Function | File | Line | Method? |
|----------|------|------|---------|
| `src.api.admin.document_manager.DocumentManager.bulk_delete` | `src/api/admin/document_manager.py` | 211 | Yes |
| `src.api.admin.document_manager.DocumentManager.upload_document` | `src/api/admin/document_manager.py` | 258 | Yes |
| `src.api.admin.document_manager.DocumentManager.validate_file` | `src/api/admin/document_manager.py` | 379 | Yes |
| `src.api.api.get_version` | `src/api/api.py` | 150 | No |
| `src.api.api.cleanup_old_attachments` | `src/api/api.py` | 198 | No |
| `src.api.api.require_auth` | `src/api/api.py` | 223 | No |
| `src.api.api.require_admin` | `src/api/api.py` | 256 | No |
| `src.api.api.root` | `src/api/api.py` | 377 | No |
| `src.api.api.admin_panel` | `src/api/api.py` | 412 | No |
| `src.api.api.get_config` | `src/api/api.py` | 487 | No |
| `src.api.api.get_example_questions` | `src/api/api.py` | 519 | No |
| `src.api.api.health_check` | `src/api/api.py` | 552 | No |
| `src.api.api.startup_event` | `src/api/api.py` | 559 | No |
| `src.api.api.shutdown_event` | `src/api/api.py` | 577 | No |
| `src.api.auth.otp_manager.OTPManager.cleanup_expired` | `src/api/auth/otp_manager.py` | 96 | Yes |
| `src.api.auth.session_manager.SessionManager.cleanup_inactive_sessions` | `src/api/auth/session_manager.py` | 227 | Yes |
| `src.api.routes.admin.create_admin_router.get_document_descriptions` | `src/api/routes/admin.py` | 144 | No |
| `src.api.routes.admin.create_admin_router.view_document` | `src/api/routes/admin.py` | 237 | No |
| `src.api.routes.admin.create_admin_router.download_document` | `src/api/routes/admin.py` | 305 | No |
| `src.api.routes.admin.create_admin_router.upload_document` | `src/api/routes/admin.py` | 391 | No |
| `src.api.routes.admin.create_admin_router.list_crawled_urls` | `src/api/routes/admin.py` | 654 | No |
| `src.api.routes.admin.create_admin_router.delete_all_crawled_urls` | `src/api/routes/admin.py` | 695 | No |
| `src.api.routes.admin.create_admin_router.delete_crawled_url` | `src/api/routes/admin.py` | 773 | No |
| `src.api.routes.admin.create_admin_router.create_backup.create_and_notify` | `src/api/routes/admin.py` | 870 | No |
| `src.api.routes.admin.create_admin_router.download_backup` | `src/api/routes/admin.py` | 996 | No |
| `src.api.routes.admin.create_admin_router.get_prompt_settings` | `src/api/routes/admin.py` | 1105 | No |
| `src.api.routes.admin.create_admin_router.update_prompt_settings` | `src/api/routes/admin.py` | 1157 | No |
| `src.api.routes.admin.create_admin_router.get_model_settings` | `src/api/routes/admin.py` | 1219 | No |
| `src.api.routes.admin.create_admin_router.generate_example_questions_endpoint` | `src/api/routes/admin.py` | 1276 | No |
| `src.api.routes.analytics.create_analytics_router.get_feedback_analytics` | `src/api/routes/analytics.py` | 303 | No |
| `src.api.routes.analytics.create_analytics_router.cluster_query_topics` | `src/api/routes/analytics.py` | 434 | No |
| `src.api.routes.analytics.create_analytics_router.get_kb_health` | `src/api/routes/analytics.py` | 513 | No |
| `src.api.routes.auth.create_auth_router.request_otp` | `src/api/routes/auth.py` | 90 | No |
| `src.api.routes.auth.create_auth_router.auth_status` | `src/api/routes/auth.py` | 297 | No |
| `src.api.routes.conversations.create_conversations_router.get_history` | `src/api/routes/conversations.py` | 53 | No |
| `src.api.routes.conversations.create_conversations_router.clear_session` | `src/api/routes/conversations.py` | 75 | No |
| `src.api.routes.conversations.create_conversations_router.list_conversations` | `src/api/routes/conversations.py` | 99 | No |
| `src.api.routes.conversations.create_conversations_router.get_conversation_messages` | `src/api/routes/conversations.py` | 186 | No |
| `src.api.routes.conversations.create_conversations_router.delete_conversation` | `src/api/routes/conversations.py` | 268 | No |
| `src.api.routes.conversations.create_conversations_router.search_conversations` | `src/api/routes/conversations.py` | 323 | No |
| `src.api.routes.feedback.create_feedback_router.feedback_page` | `src/api/routes/feedback.py` | 110 | No |
| `src.api.routes.feedback.create_feedback_router.submit_email_feedback` | `src/api/routes/feedback.py` | 118 | No |
| `src.api.routes.feedback.create_feedback_router.submit_feedback` | `src/api/routes/feedback.py` | 162 | No |
| `src.api.routes.onboarding.create_onboarding_router.validate_code` | `src/api/routes/onboarding.py` | 160 | No |
| `src.api.routes.onboarding.create_onboarding_router.join_tenant` | `src/api/routes/onboarding.py` | 191 | No |
| `src.api.routes.onboarding.create_onboarding_router.slug_check` | `src/api/routes/onboarding.py` | 333 | No |
| `src.api.routes.query.create_query_router.download_attachment` | `src/api/routes/query.py` | 275 | No |
| `src.api.routes.team.create_team_router.list_team_members` | `src/api/routes/team.py` | 38 | No |
| `src.api.routes.team.create_team_router.update_team_member` | `src/api/routes/team.py` | 162 | No |
| `src.api.routes.tenant_admin.create_tenant_admin_router.get_tenant_details` | `src/api/routes/tenant_admin.py` | 52 | No |
| `src.api.routes.tenant_admin.create_tenant_admin_router.get_invite_info` | `src/api/routes/tenant_admin.py` | 75 | No |
| `src.api.routes.tenant_admin.create_tenant_admin_router.regenerate_invite_code` | `src/api/routes/tenant_admin.py` | 96 | No |
| `src.api.routes.tenant_admin.create_tenant_admin_router.update_tenant_settings` | `src/api/routes/tenant_admin.py` | 122 | No |
| `src.api.routes.tenant_admin.create_tenant_admin_router.list_join_requests` | `src/api/routes/tenant_admin.py` | 202 | No |
| `src.api.routes.tenant_admin.create_tenant_admin_router.approve_join_request` | `src/api/routes/tenant_admin.py` | 221 | No |
| `src.api.routes.tenant_admin.create_tenant_admin_router.reject_join_request` | `src/api/routes/tenant_admin.py` | 304 | No |
| `src.api.routes.tenant_admin.create_tenant_admin_router.get_invite_qr` | `src/api/routes/tenant_admin.py` | 351 | No |
| `src.cli.commands.backup.cleanup_backups` | `src/cli/commands/backup.py` | 152 | No |
| `src.cli.commands.db.init_database` | `src/cli/commands/db.py` | 37 | No |
| `src.cli.commands.db.test_connection` | `src/cli/commands/db.py` | 63 | No |
| `src.cli.commands.db.show_info` | `src/cli/commands/db.py` | 93 | No |
| `src.cli.commands.db.show_stats` | `src/cli/commands/db.py` | 124 | No |
| `src.cli.commands.db.cleanup_records` | `src/cli/commands/db.py` | 220 | No |
| `src.cli.commands.kb.show_stats` | `src/cli/commands/kb.py` | 84 | No |
| `src.cli.commands.kb.reingest_documents` | `src/cli/commands/kb.py` | 147 | No |
| `src.cli.commands.kb.clear_knowledge_base` | `src/cli/commands/kb.py` | 266 | No |
| `src.cli.commands.kb.regenerate_descriptions` | `src/cli/commands/kb.py` | 301 | No |
| `src.cli.commands.kb.query_kb` | `src/cli/commands/kb.py` | 401 | No |
| `src.cli.main.show_version` | `src/cli/main.py` | 68 | No |
| `src.cli.main.show_info` | `src/cli/main.py` | 88 | No |
| `src.cli.main.cli` | `src/cli/main.py` | 134 | No |
| `src.cli.utils.print_panel` | `src/cli/utils.py` | 77 | No |
| `src.config.Settings.ensure_directories` | `src/config.py` | 466 | Yes |
| `src.document_processing.description_generator.DescriptionGenerator.get_description` | `src/document_processing/description_generator.py` | 205 | Yes |
| `src.document_processing.document_processor.DocumentProcessor.extract_text_from_pdf` | `src/document_processing/document_processor.py` | 107 | Yes |
| `src.document_processing.document_processor.DocumentProcessor.extract_text_from_docx` | `src/document_processing/document_processor.py` | 132 | Yes |
| `src.document_processing.document_processor.DocumentProcessor.extract_text_from_txt` | `src/document_processing/document_processor.py` | 156 | Yes |
| `src.document_processing.document_processor.DocumentProcessor.extract_text_from_csv` | `src/document_processing/document_processor.py` | 184 | Yes |
| `src.document_processing.document_processor.DocumentProcessor.extract_text_from_excel` | `src/document_processing/document_processor.py` | 279 | Yes |
| `src.document_processing.document_processor.DocumentProcessor.extract_text` | `src/document_processing/document_processor.py` | 393 | Yes |
| `src.document_processing.enhancement_processor.EnhancementProcessor.expand_structured_data` | `src/document_processing/enhancement_processor.py` | 122 | Yes |
| `src.document_processing.enhancement_processor.EnhancementProcessor.generate_qa_pairs` | `src/document_processing/enhancement_processor.py` | 173 | Yes |
| `src.document_processing.file_watcher.DocumentEventHandler.on_created` | `src/document_processing/file_watcher.py` | 58 | Yes |
| `src.document_processing.file_watcher.DocumentEventHandler.on_modified` | `src/document_processing/file_watcher.py` | 91 | Yes |
| `src.document_processing.file_watcher.DocumentEventHandler.on_deleted` | `src/document_processing/file_watcher.py` | 137 | Yes |
| `src.document_processing.file_watcher.FileWatcher.run_forever` | `src/document_processing/file_watcher.py` | 239 | Yes |
| `src.document_processing.file_watcher.FileWatcher.initial_scan` | `src/document_processing/file_watcher.py` | 252 | Yes |
| `src.document_processing.kb_manager.KnowledgeBaseManager.clear_all` | `src/document_processing/kb_manager.py` | 645 | Yes |
| `src.document_processing.web_crawler.WebCrawler.normalize_url` | `src/document_processing/web_crawler.py` | 62 | Yes |
| `src.document_processing.web_crawler.WebCrawler.get_url_hash` | `src/document_processing/web_crawler.py` | 112 | Yes |
| `src.document_processing.web_crawler.WebCrawler.validate_url` | `src/document_processing/web_crawler.py` | 125 | Yes |
| `src.document_processing.web_crawler.WebCrawler.fetch_html` | `src/document_processing/web_crawler.py` | 142 | Yes |
| `src.document_processing.web_crawler.WebCrawler.extract_content` | `src/document_processing/web_crawler.py` | 202 | Yes |
| `src.document_processing.web_crawler.WebCrawler.extract_links` | `src/document_processing/web_crawler.py` | 253 | Yes |
| `src.email.attachment_handler.AttachmentHandler.validate_file_type` | `src/email/attachment_handler.py` | 181 | Yes |
| `src.email.attachment_handler.AttachmentHandler.validate_file_size` | `src/email/attachment_handler.py` | 208 | Yes |
| `src.email.attachment_handler.AttachmentHandler.save_attachment_from_bytes` | `src/email/attachment_handler.py` | 319 | Yes |
| `src.email.attachment_handler.AttachmentHandler.get_temp_dir_size` | `src/email/attachment_handler.py` | 569 | Yes |
| `src.email.conversation_manager.ConversationManager.get_or_create_conversation` | `src/email/conversation_manager.py` | 113 | Yes |
| `src.email.conversation_manager.ConversationManager.get_conversation_history` | `src/email/conversation_manager.py` | 259 | Yes |
| `src.email.conversation_manager.ConversationManager.set_message_rating` | `src/email/conversation_manager.py` | 354 | Yes |
| `src.email.conversation_manager.ConversationManager.get_conversation_stats` | `src/email/conversation_manager.py` | 391 | Yes |
| `src.email.conversation_manager.ConversationManager.delete_conversation` | `src/email/conversation_manager.py` | 435 | Yes |
| `src.email.conversation_manager.ConversationManager.get_message_optimization_details` | `src/email/conversation_manager.py` | 665 | Yes |
| `src.email.conversation_manager.ConversationManager.get_message_source_details` | `src/email/conversation_manager.py` | 697 | Yes |
| `src.email.db_manager.DatabaseManager.drop_all` | `src/email/db_manager.py` | 74 | Yes |
| `src.email.email_client.EmailClient.disconnect` | `src/email/email_client.py` | 139 | Yes |
| `src.email.email_client.EmailClient.reconnect` | `src/email/email_client.py` | 179 | Yes |
| `src.email.email_client.EmailClient.ensure_connected` | `src/email/email_client.py` | 213 | Yes |
| `src.email.email_client.EmailClient.mark_unseen` | `src/email/email_client.py` | 288 | Yes |
| `src.email.email_client.EmailClient.get_folder_list` | `src/email/email_client.py` | 309 | Yes |
| `src.email.email_client.EmailClient.get_message_count` | `src/email/email_client.py` | 330 | Yes |
| `src.email.email_client.EmailClient.__exit__` | `src/email/email_client.py` | 366 | Yes |
| `src.email.email_parser.EmailMessage.has_body` | `src/email/email_parser.py` | 132 | Yes |
| `src.email.email_parser.EmailParser.parse_email_address` | `src/email/email_parser.py` | 203 | Yes |
| `src.email.email_parser.EmailParser.parse_email_list` | `src/email/email_parser.py` | 228 | Yes |
| `src.email.email_parser.EmailParser.html_to_text` | `src/email/email_parser.py` | 260 | Yes |
| `src.email.email_parser.EmailParser.strip_signature` | `src/email/email_parser.py` | 283 | Yes |
| `src.email.email_parser.EmailParser.extract_body` | `src/email/email_parser.py` | 362 | Yes |
| `src.email.email_parser.EmailParser.is_cced_message` | `src/email/email_parser.py` | 401 | Yes |
| `src.email.email_parser.EmailParser.is_addressed_to_teach` | `src/email/email_parser.py` | 417 | Yes |
| `src.email.email_parser.EmailParser.is_forwarded` | `src/email/email_parser.py` | 446 | Yes |
| `src.email.email_processor.EmailProcessor.process_message` | `src/email/email_processor.py` | 119 | Yes |
| `src.email.email_processor.EmailProcessor.cleanup_old_temp_files` | `src/email/email_processor.py` | 1172 | Yes |
| `src.email.email_processor.EmailProcessor.get_processing_stats` | `src/email/email_processor.py` | 1184 | Yes |
| `src.email.email_sender.generate_feedback_token` | `src/email/email_sender.py` | 24 | No |
| `src.email.email_sender.generate_feedback_urls` | `src/email/email_sender.py` | 57 | No |
| `src.email.email_sender.load_custom_footer` | `src/email/email_sender.py` | 82 | No |
| `src.email.email_sender._format_html_email.format_source_display` | `src/email/email_sender.py` | 504 | No |
| `src.email.email_sender.format_welcome_email` | `src/email/email_sender.py` | 617 | No |
| `src.email.email_service.EmailService.is_running` | `src/email/email_service.py` | 243 | Yes |
| `src.email.email_service.EmailService.get_status` | `src/email/email_service.py` | 252 | Yes |
| `src.email.email_service.main` | `src/email/email_service.py` | 269 | No |
| `src.email.tenant_email_router.TenantEmailRouter.get_tenant_context` | `src/email/tenant_email_router.py` | 130 | Yes |
| `src.platform.bootstrap.auto_provision_default_tenant` | `src/platform/bootstrap.py` | 33 | No |
| `src.platform.component_factory.TenantComponentFactory.evict` | `src/platform/component_factory.py` | 175 | Yes |
| `src.platform.db_manager.TenantDBManager.get_tenant_session` | `src/platform/db_manager.py` | 249 | Yes |
| `src.platform.db_manager.TenantDBManager.get_tenant_by_email` | `src/platform/db_manager.py` | 317 | Yes |
| `src.platform.db_manager.TenantDBManager.get_active_tenants` | `src/platform/db_manager.py` | 338 | Yes |
| `src.platform.encryption.KeyManager.get_tenant_key` | `src/platform/encryption.py` | 30 | Yes |
| `src.platform.encryption.KeyManager.create_tenant_key` | `src/platform/encryption.py` | 46 | Yes |
| `src.platform.encryption.KeyManager.destroy_tenant_key` | `src/platform/encryption.py` | 61 | Yes |
| `src.platform.encryption.KeyManager.rotate_tenant_key` | `src/platform/encryption.py` | 73 | Yes |
| `src.platform.encryption.DatabaseKeyManager.get_tenant_key` | `src/platform/encryption.py` | 136 | Yes |
| `src.platform.encryption.DatabaseKeyManager.create_tenant_key` | `src/platform/encryption.py` | 142 | Yes |
| `src.platform.encryption.DatabaseKeyManager.destroy_tenant_key` | `src/platform/encryption.py` | 146 | Yes |
| `src.platform.encryption.DatabaseKeyManager.rotate_tenant_key` | `src/platform/encryption.py` | 150 | Yes |
| `src.platform.encryption.DatabaseKeyManager.get_tenant_key_with_session` | `src/platform/encryption.py` | 154 | Yes |
| `src.platform.encryption.TenantEncryptor.encrypt` | `src/platform/encryption.py` | 302 | Yes |
| `src.platform.encryption.TenantEncryptor.decrypt` | `src/platform/encryption.py` | 318 | Yes |
| `src.platform.models.generate_uuid` | `src/platform/models.py` | 50 | No |
| `src.platform.storage.StorageBackend.list_keys` | `src/platform/storage.py` | 88 | Yes |
| `src.platform.storage.LocalStorageBackend.list_keys` | `src/platform/storage.py` | 207 | Yes |
| `src.platform.storage.S3StorageBackend.list_keys` | `src/platform/storage.py` | 358 | Yes |
| `src.platform_admin.app.root` | `src/platform_admin/app.py` | 110 | No |
| `src.platform_admin.app.shutdown` | `src/platform_admin/app.py` | 118 | No |
| `src.platform_admin.routes.auth.create_admin_auth_router.request_otp` | `src/platform_admin/routes/auth.py` | 146 | No |
| `src.platform_admin.routes.auth.create_admin_auth_router.auth_status` | `src/platform_admin/routes/auth.py` | 255 | No |
| `src.platform_admin.routes.health.create_health_router.platform_health` | `src/platform_admin/routes/health.py` | 37 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.list_tenants` | `src/platform_admin/routes/tenants.py` | 113 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.get_tenant` | `src/platform_admin/routes/tenants.py` | 156 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.suspend_tenant` | `src/platform_admin/routes/tenants.py` | 266 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.resume_tenant` | `src/platform_admin/routes/tenants.py` | 287 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.delete_tenant` | `src/platform_admin/routes/tenants.py` | 308 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.rotate_key` | `src/platform_admin/routes/tenants.py` | 342 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.list_users` | `src/platform_admin/routes/tenants.py` | 376 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.add_user` | `src/platform_admin/routes/tenants.py` | 405 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.remove_user` | `src/platform_admin/routes/tenants.py` | 442 | No |
| `src.platform_admin.routes.tenants.create_tenants_router.get_tenant_stats` | `src/platform_admin/routes/tenants.py` | 468 | No |
| `src.rag.example_questions.generate_example_questions` | `src/rag/example_questions.py` | 26 | No |
| `src.rag.example_questions.save_example_questions` | `src/rag/example_questions.py` | 114 | No |
| `src.rag.tools.base.Tool.to_openai_function` | `src/rag/tools/base.py` | 68 | Yes |
| `src.rag.tools.base.ToolRegistry.register` | `src/rag/tools/base.py` | 140 | Yes |
| `src.rag.tools.tool_executor.ToolExecutor.execute_function_call` | `src/rag/tools/tool_executor.py` | 32 | Yes |
| `src.rag.tools.tool_executor.ToolExecutor.get_tool_descriptions` | `src/rag/tools/tool_executor.py` | 131 | Yes |
