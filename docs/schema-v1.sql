-- MySQL 8.0.16+；结构参考。正式建表使用 Alembic 迁移，见 database-migrations.md。


CREATE TABLE users (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL COMMENT '仅保存密码哈希', 
	`role` VARCHAR(8) NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT uq_users_username UNIQUE (username), 
	CONSTRAINT ck_users_userrole CHECK (`role` IN ('customer', 'admin'))
)

;


CREATE TABLE conversations (
	id VARCHAR(36) NOT NULL, 
	user_id BIGINT NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	CONSTRAINT pk_conversations PRIMARY KEY (id), 
	CONSTRAINT fk_conversations_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_conversations_user_updated ON conversations (user_id, updated_at);


CREATE TABLE orders (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	order_no VARCHAR(64) NOT NULL, 
	user_id BIGINT NOT NULL, 
	paid_amount_cents BIGINT NOT NULL, 
	payment_status VARCHAR(8) NOT NULL, 
	fulfillment_status VARCHAR(9) NOT NULL, 
	paid_at DATETIME(6), 
	shipped_at DATETIME(6), 
	delivered_at DATETIME(6), 
	tracking_no VARCHAR(100), 
	created_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	CONSTRAINT pk_orders PRIMARY KEY (id), 
	CONSTRAINT ck_orders_nonnegative_paid_amount CHECK (paid_amount_cents >= 0), 
	CONSTRAINT uq_orders_order_no UNIQUE (order_no), 
	CONSTRAINT fk_orders_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_orders_paymentstatus CHECK (payment_status IN ('unpaid', 'paid', 'refunded')), 
	CONSTRAINT ck_orders_fulfillmentstatus CHECK (fulfillment_status IN ('unshipped', 'shipped', 'delivered'))
)

;

CREATE INDEX ix_orders_user_created ON orders (user_id, created_at);


CREATE TABLE order_items (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	order_id BIGINT NOT NULL, 
	product_code VARCHAR(64) NOT NULL, 
	product_name VARCHAR(200) NOT NULL, 
	product_model VARCHAR(100), 
	quantity INTEGER NOT NULL, 
	unit_price_cents BIGINT NOT NULL, 
	created_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	CONSTRAINT pk_order_items PRIMARY KEY (id), 
	CONSTRAINT ck_order_items_positive_quantity CHECK (quantity > 0), 
	CONSTRAINT ck_order_items_nonnegative_unit_price CHECK (unit_price_cents >= 0), 
	CONSTRAINT fk_order_items_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_order_items_order_id ON order_items (order_id);


CREATE TABLE refund_requests (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	request_key VARCHAR(64) NOT NULL COMMENT '服务端稳定操作ID，重试复用', 
	order_id BIGINT NOT NULL, 
	conversation_id VARCHAR(36) NOT NULL, 
	amount_cents BIGINT NOT NULL, 
	reason_original TEXT NOT NULL, 
	reason_category VARCHAR(64), 
	status VARCHAR(8) NOT NULL, 
	active_order_id BIGINT GENERATED ALWAYS AS (CASE WHEN status IN ('pending', 'approved', 'refunded') THEN order_id ELSE NULL END) STORED, 
	created_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	CONSTRAINT pk_refund_requests PRIMARY KEY (id), 
	CONSTRAINT ck_refund_requests_positive_amount CHECK (amount_cents > 0), 
	CONSTRAINT ck_refund_requests_nonblank_reason CHECK (length(trim(reason_original)) > 0), 
	CONSTRAINT uq_refund_requests_request_key UNIQUE (request_key), 
	CONSTRAINT fk_refund_requests_order_id_orders FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_refund_requests_conversation_id_conversations FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_refund_requests_refundstatus CHECK (status IN ('pending', 'approved', 'rejected', 'refunded')), 
	CONSTRAINT uq_refund_requests_active_order_id UNIQUE (active_order_id)
)

;

CREATE INDEX ix_refund_requests_conversation_id ON refund_requests (conversation_id);

CREATE INDEX ix_refund_requests_order_created ON refund_requests (order_id, created_at);

CREATE INDEX ix_refund_requests_status_created ON refund_requests (status, created_at);


CREATE TABLE refund_approvals (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	refund_request_id BIGINT NOT NULL, 
	admin_id BIGINT NOT NULL, 
	decision VARCHAR(8) NOT NULL, 
	comment TEXT, 
	created_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	CONSTRAINT pk_refund_approvals PRIMARY KEY (id), 
	CONSTRAINT uq_refund_approvals_refund_request_id UNIQUE (refund_request_id), 
	CONSTRAINT fk_refund_approvals_refund_request_id_refund_requests FOREIGN KEY(refund_request_id) REFERENCES refund_requests (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_refund_approvals_admin_id_users FOREIGN KEY(admin_id) REFERENCES users (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_refund_approvals_approvaldecision CHECK (decision IN ('approved', 'rejected'))
)

;

CREATE INDEX ix_refund_approvals_admin_id ON refund_approvals (admin_id);


CREATE TABLE refund_records (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	refund_request_id BIGINT NOT NULL, 
	refund_no VARCHAR(64) NOT NULL, 
	amount_cents BIGINT NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	attempt_count INTEGER NOT NULL, 
	last_error TEXT, 
	succeeded_at DATETIME(6), 
	created_at DATETIME(6) NOT NULL, 
	updated_at DATETIME(6) NOT NULL, 
	CONSTRAINT pk_refund_records PRIMARY KEY (id), 
	CONSTRAINT ck_refund_records_positive_amount CHECK (amount_cents > 0), 
	CONSTRAINT ck_refund_records_nonnegative_attempts CHECK (attempt_count >= 0), 
	CONSTRAINT uq_refund_records_refund_request_id UNIQUE (refund_request_id), 
	CONSTRAINT fk_refund_records_refund_request_id_refund_requests FOREIGN KEY(refund_request_id) REFERENCES refund_requests (id) ON DELETE RESTRICT, 
	CONSTRAINT uq_refund_records_refund_no UNIQUE (refund_no), 
	CONSTRAINT ck_refund_records_refundexecutionstatus CHECK (status IN ('processing', 'succeeded', 'failed'))
)

;
