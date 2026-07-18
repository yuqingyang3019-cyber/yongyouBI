import { BellOutlined, DeleteOutlined, SendOutlined } from "@ant-design/icons";
import {
  Button,
  Drawer,
  Form,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  TimePicker,
  Tooltip,
  message
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useEffect, useRef, useState } from "react";

import {
  createNotificationTask,
  deleteNotificationTask,
  fetchNotificationTasks,
  searchDingTalkContacts,
  searchDingTalkDepartments,
  setNotificationTaskEnabled,
  type DingTalkContact,
  type DingTalkDepartment,
  type NotificationSchedule,
  type NotificationTask
} from "../receivables/api";

interface FormValues {
  recipientUserids: string[];
  recipientDepartmentIds: number[];
  kind: NotificationSchedule["kind"];
  interval: number;
  time: Dayjs;
  weekday: number;
}

const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

function scheduleText(schedule: NotificationSchedule): string {
  if (schedule.kind === "minutes") return `每 ${schedule.interval} 分钟`;
  if (schedule.kind === "hours") return `每 ${schedule.interval} 小时`;
  const time = `${String(schedule.hour).padStart(2, "0")}:${String(schedule.minute).padStart(2, "0")}`;
  return schedule.kind === "daily" ? `每天 ${time}` : `每${WEEKDAYS[schedule.weekday]} ${time}`;
}

function dateTime(value: string): string {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "—";
}

export function NotificationManager() {
  const [form] = Form.useForm<FormValues>();
  const kind = Form.useWatch("kind", form);
  const searchTimer = useRef<number | undefined>(undefined);
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [contacts, setContacts] = useState<DingTalkContact[]>([]);
  const [departments, setDepartments] = useState<DingTalkDepartment[]>([]);
  const [tasks, setTasks] = useState<NotificationTask[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [loadingTasks, setLoadingTasks] = useState(false);

  function loadTasks() {
    setLoadingTasks(true);
    return fetchNotificationTasks()
      .then(setTasks)
      .catch((cause: unknown) => message.error(cause instanceof Error ? cause.message : "通知任务加载失败"))
      .finally(() => setLoadingTasks(false));
  }

  useEffect(() => {
    if (drawerOpen) loadTasks();
  }, [drawerOpen]);

  function searchContacts(keyword: string) {
    window.clearTimeout(searchTimer.current);
    searchTimer.current = window.setTimeout(() => {
      searchDingTalkContacts(keyword)
        .then(setContacts)
        .catch((cause: unknown) => message.error(cause instanceof Error ? cause.message : "通讯录搜索失败"));
    }, 300);
  }

  function searchDepartments(keyword: string) {
    searchDingTalkDepartments(keyword)
      .then(setDepartments)
      .catch((cause: unknown) => message.error(cause instanceof Error ? cause.message : "部门搜索失败"));
  }

  function openCreate() {
    form.setFieldsValue({
      recipientUserids: [],
      recipientDepartmentIds: [],
      kind: "daily",
      interval: 1,
      time: dayjs().hour(9).minute(0),
      weekday: 0
    });
    setContacts([]);
    setDepartments([]);
    setModalOpen(true);
    searchContacts("");
    searchDepartments("");
  }

  async function submit() {
    const values = await form.validateFields();
    const schedule: NotificationSchedule = {
      kind: values.kind,
      interval: values.interval || 1,
      hour: values.time?.hour() ?? 9,
      minute: values.time?.minute() ?? 0,
      weekday: values.weekday ?? 0
    };
    setSubmitting(true);
    try {
      const result = await createNotificationTask(
        values.recipientUserids ?? [],
        values.recipientDepartmentIds ?? [],
        schedule
      );
      setModalOpen(false);
      if (result.immediate.success) {
        message.success("已立即发送逾期摘要，并创建定时任务");
      } else {
        message.warning(result.immediate.error || "任务已创建，但首次发送失败");
      }
      await loadTasks();
      setDrawerOpen(true);
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "创建通知任务失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function toggle(task: NotificationTask, enabled: boolean) {
    try {
      const updated = await setNotificationTaskEnabled(task.id, enabled);
      setTasks((items) => items.map((item) => item.id === updated.id ? updated : item));
      message.success(enabled ? "任务已启用" : "任务已暂停");
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "任务更新失败");
    }
  }

  async function remove(task: NotificationTask) {
    try {
      await deleteNotificationTask(task.id);
      setTasks((items) => items.filter((item) => item.id !== task.id));
      message.success("任务已删除");
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : "任务删除失败");
    }
  }

  return (
    <>
      <Button icon={<SendOutlined />} onClick={openCreate}>发送逾期摘要</Button>
      <Button icon={<BellOutlined />} onClick={() => setDrawerOpen(true)}>通知任务</Button>
      <Modal
        title="发送并定时推送逾期摘要"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={submit}
        okText="立即发送并创建任务"
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="recipientUserids"
            label="指定接收人"
            rules={[{ type: "array", max: 20, message: "最多选择 20 人" }]}
          >
            <Select
              mode="multiple"
              showSearch
              filterOption={false}
              onSearch={searchContacts}
              placeholder="输入姓名或部门搜索钉钉通讯录"
              options={contacts.map((contact) => ({
                value: contact.userid,
                label: `${contact.name}${contact.department ? ` · ${contact.department}` : ""}`
              }))}
            />
          </Form.Item>
          <Form.Item name="recipientDepartmentIds" label="接收部门">
            <Select
              mode="multiple"
              showSearch
              filterOption={false}
              onSearch={searchDepartments}
              placeholder="输入部门名称搜索；定时发送时自动读取当前成员"
              options={departments.map((department) => ({
                value: department.departmentId,
                label: department.name
              }))}
            />
          </Form.Item>
          <Form.Item name="kind" label="发送频率" rules={[{ required: true }]}>
            <Select options={[
              { value: "minutes", label: "每 N 分钟" },
              { value: "hours", label: "每 N 小时" },
              { value: "daily", label: "每天" },
              { value: "weekly", label: "每周" }
            ]} />
          </Form.Item>
          {kind === "minutes" || kind === "hours" ? (
            <Form.Item name="interval" label={kind === "minutes" ? "分钟间隔" : "小时间隔"} rules={[{ required: true }]}>
              <InputNumber min={1} max={kind === "minutes" ? 1440 : 168} precision={0} style={{ width: "100%" }} />
            </Form.Item>
          ) : null}
          {kind === "weekly" ? (
            <Form.Item name="weekday" label="星期" rules={[{ required: true }]}>
              <Select options={WEEKDAYS.map((label, value) => ({ label, value }))} />
            </Form.Item>
          ) : null}
          {kind === "daily" || kind === "weekly" ? (
            <Form.Item name="time" label="发送时间" rules={[{ required: true }]}>
              <TimePicker format="HH:mm" minuteStep={5} style={{ width: "100%" }} />
            </Form.Item>
          ) : null}
        </Form>
      </Modal>
      <Drawer title="逾期摘要通知任务" width={760} open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <Table<NotificationTask>
          rowKey="id"
          loading={loadingTasks}
          dataSource={tasks}
          pagination={false}
          scroll={{ x: 700 }}
          columns={[
            {
              title: "接收人",
              render: (_, task) => task.recipients.map((item) => item.name).join("、")
            },
            { title: "频率", render: (_, task) => scheduleText(task.schedule), width: 130 },
            {
              title: "执行状态",
              width: 150,
              render: (_, task) => (
                <Space direction="vertical" size={0}>
                  <Tag color={task.lastStatus === "failed" ? "error" : task.lastStatus === "success" ? "success" : "default"}>
                    {task.lastStatus === "failed" ? "上次失败" : task.lastStatus === "success" ? "上次成功" : "等待执行"}
                  </Tag>
                  {task.lastError ? <Tooltip title={task.lastError}>查看错误</Tooltip> : null}
                </Space>
              )
            },
            {
              title: "下次执行",
              dataIndex: "nextRunAt",
              render: (value, task) => task.enabled ? dateTime(value) : "已暂停",
              width: 150
            },
            {
              title: "操作",
              width: 100,
              fixed: "right",
              render: (_, task) => (
                <Space>
                  <Switch size="small" checked={task.enabled} onChange={(value) => toggle(task, value)} />
                  <Popconfirm title="确认删除此通知任务？" onConfirm={() => remove(task)}>
                    <Button type="text" danger size="small" icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              )
            }
          ]}
        />
      </Drawer>
    </>
  );
}
