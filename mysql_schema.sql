CREATE TABLE IF NOT EXISTS vms_meta (
  `key` varchar(80) NOT NULL,
  `value` longtext NOT NULL,
  PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vms_employee (
  id varchar(80) NOT NULL,
  name varchar(80) NOT NULL,
  department varchar(120) NOT NULL,
  phone varchar(40) NOT NULL,
  email varchar(160) NOT NULL,
  manager_id varchar(80) NOT NULL,
  manager_name varchar(80) NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vms_user (
  username varchar(80) NOT NULL,
  display_name varchar(80) NOT NULL,
  role varchar(40) NOT NULL,
  password_hash varchar(128) NOT NULL,
  permissions_json longtext NOT NULL,
  created_at varchar(40) NOT NULL,
  updated_at varchar(40) NOT NULL,
  PRIMARY KEY (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vms_appointment (
  application_no varchar(40) NOT NULL,
  visitor_type varchar(40) NOT NULL,
  applicant_name varchar(80) NOT NULL,
  applicant_company varchar(200) NOT NULL,
  applicant_phone varchar(40) NOT NULL,
  applicant_email varchar(160) NULL,
  contact_employee_id varchar(80) NOT NULL,
  contact_name varchar(80) NOT NULL,
  contact_department varchar(120) NOT NULL,
  contact_phone varchar(40) NOT NULL,
  contact_email varchar(160) NOT NULL,
  apply_date varchar(20) NOT NULL,
  visit_start_date varchar(20) NOT NULL,
  visit_end_date varchar(20) NOT NULL,
  visit_time_slot varchar(40) NOT NULL,
  visit_areas_json longtext NOT NULL,
  visit_purpose longtext NOT NULL,
  need_parking tinyint(1) NOT NULL,
  car_plate varchar(40) NULL,
  car_visitor_name varchar(80) NULL,
  special_request longtext NULL,
  oa_instance_id varchar(120) NULL,
  oa_form_url varchar(500) NULL,
  status varchar(40) NOT NULL,
  approved_at varchar(40) NULL,
  created_at varchar(40) NOT NULL,
  updated_at varchar(40) NOT NULL,
  current_node_index int NOT NULL DEFAULT 0,
  approval_nodes_json longtext NOT NULL,
  logs_json longtext NULL,
  oa_sync_status varchar(40) NULL,
  oa_submitted_at varchar(40) NULL,
  oa_last_error longtext NULL,
  oa_status varchar(80) NULL,
  PRIMARY KEY (application_no),
  KEY ix_vms_appointment_status (status),
  KEY ix_vms_appointment_visit_date (visit_start_date, visit_end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vms_appointment_visitor (
  visitor_id varchar(80) NOT NULL,
  application_no varchar(40) NOT NULL,
  seq int NOT NULL,
  name varchar(80) NOT NULL,
  company varchar(200) NOT NULL,
  phone varchar(40) NOT NULL,
  title varchar(80) NULL,
  id_type varchar(40) NOT NULL,
  id_number_masked varchar(80) NOT NULL,
  id_number_hash varchar(128) NOT NULL,
  id_last4 varchar(8) NOT NULL,
  car_plate varchar(40) NULL,
  qr_token varchar(120) NULL,
  qr_payload varchar(160) NULL,
  qr_status varchar(40) NOT NULL,
  checkin_time varchar(40) NULL,
  checkout_time varchar(40) NULL,
  guard_checkin_user varchar(80) NULL,
  guard_checkout_user varchar(80) NULL,
  gate_code varchar(80) NULL,
  PRIMARY KEY (visitor_id),
  KEY ix_vms_visitor_application (application_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vms_approval_record (
  id bigint NOT NULL AUTO_INCREMENT,
  application_no varchar(40) NOT NULL,
  node_name varchar(80) NOT NULL,
  approver_id varchar(80) NULL,
  approver_name varchar(80) NULL,
  action varchar(40) NOT NULL,
  opinion longtext NULL,
  action_time varchar(40) NOT NULL,
  PRIMARY KEY (id),
  KEY ix_vms_approval_application (application_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vms_agreement_confirm (
  id bigint NOT NULL AUTO_INCREMENT,
  application_no varchar(40) NOT NULL,
  agreement_type varchar(40) NOT NULL,
  item_code varchar(40) NOT NULL,
  item_content longtext NOT NULL,
  confirmed tinyint(1) NOT NULL,
  confirmed_at varchar(40) NOT NULL,
  PRIMARY KEY (id),
  KEY ix_vms_agreement_application (application_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vms_operation_log (
  id bigint NOT NULL AUTO_INCREMENT,
  action varchar(80) NOT NULL,
  application_no varchar(40) NULL,
  `user` varchar(80) NULL,
  detail_json longtext NULL,
  `time` varchar(40) NOT NULL,
  PRIMARY KEY (id),
  KEY ix_vms_operation_application (application_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
