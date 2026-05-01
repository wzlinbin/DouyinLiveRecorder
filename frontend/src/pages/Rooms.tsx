import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Drawer, Form, Input, message, Popconfirm, Select, Space, Switch, Table } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { adminApi, getErrorMessage } from '../api/client'
import PageHeader from '../components/PageHeader'
import PlatformIcon from '../components/PlatformIcon'
import StatusBadge from '../components/StatusBadge'
import { useAppStore } from '../stores/appStore'
import type { Room } from '../types/admin'
import { asBool } from '../utils/format'

const qualityOptions = ['原画', '蓝光', '超清', '高清', '标清', '流畅']

type RoomFormValues = {
  url: string
  name: string
  quality: string
  enabled: boolean
}

function Rooms() {
  const token = useAppStore((state) => state.token)
  const [rooms, setRooms] = useState<Room[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [actionKey, setActionKey] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingRoom, setEditingRoom] = useState<Room | null>(null)
  const [form] = Form.useForm<RoomFormValues>()

  const loadRooms = useCallback(async () => {
    setLoading(true)
    try {
      setRooms(await adminApi.rooms())
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRooms()
  }, [loadRooms])

  const openCreate = () => {
    setEditingRoom(null)
    form.setFieldsValue({ url: '', name: '', quality: '原画', enabled: true })
    setDrawerOpen(true)
  }

  const openEdit = (room: Room) => {
    setEditingRoom(room)
    form.setFieldsValue({
      url: room.url,
      name: room.name,
      quality: room.quality,
      enabled: asBool(room.enabled),
    })
    setDrawerOpen(true)
  }

  const saveRoom = async (values: RoomFormValues) => {
    setSaving(true)
    try {
      if (editingRoom) {
        await adminApi.updateRoom(token, editingRoom.id, values)
        message.success('直播间已更新')
      } else {
        await adminApi.createRoom(token, values)
        message.success('直播间已创建')
      }
      setDrawerOpen(false)
      await loadRooms()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const toggleEnabled = async (room: Room, enabled: boolean) => {
    setActionKey(`toggle:${room.id}`)
    try {
      await adminApi.updateRoom(token, room.id, { enabled })
      message.success(enabled ? '已启用直播间' : '已禁用直播间')
      await loadRooms()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setActionKey(null)
    }
  }

  const startRoom = async (room: Room) => {
    setActionKey(`start:${room.id}`)
    try {
      await adminApi.startRoom(token, room.id)
      message.success('已提交开始录制命令')
      await loadRooms()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setActionKey(null)
    }
  }

  const stopRoom = async (room: Room) => {
    setActionKey(`stop:${room.id}`)
    try {
      await adminApi.stopRoom(token, room.id)
      message.success('已提交停止录制命令')
      await loadRooms()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setActionKey(null)
    }
  }

  const deleteRoom = async (room: Room) => {
    setActionKey(`delete:${room.id}`)
    try {
      await adminApi.deleteRoom(token, room.id)
      message.success('直播间已删除')
      await loadRooms()
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setActionKey(null)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="直播间管理"
        subtitle="维护直播间链接、平台、画质和启用状态，并对单个直播间快速开始或停止录制。"
        extra={
          <>
            <Button icon={<ReloadOutlined />} onClick={loadRooms}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新增直播间
            </Button>
          </>
        }
      />

      <Table<Room>
        rowKey="id"
        loading={loading}
        dataSource={rooms}
        columns={[
          {
            title: '直播间',
            dataIndex: 'name',
            render: (_, room) => (
              <Space>
                <PlatformIcon platform={room.platform} />
                <div>
                  <strong>{room.name || '未命名直播间'}</strong>
                  <div className="muted">{room.url}</div>
                </div>
              </Space>
            ),
          },
          { title: '平台', dataIndex: 'platform', width: 110 },
          { title: '清晰度', dataIndex: 'quality', width: 110 },
          {
            title: '启用',
            dataIndex: 'enabled',
            width: 100,
            render: (_, room) => (
              <Switch checked={asBool(room.enabled)} loading={actionKey === `toggle:${room.id}`} onChange={(checked) => toggleEnabled(room, checked)} />
            ),
          },
          {
            title: '状态',
            dataIndex: 'display_status',
            width: 120,
            render: (_, room) => <StatusBadge status={room.latest_job?.status || (asBool(room.enabled) ? 'idle' : 'disabled')} pulse />,
          },
          {
            title: '操作',
            width: 350,
            render: (_, room) => {
              const active = ['pending', 'probing', 'recording', 'stopping'].includes(room.latest_job?.status || '')
              return (
                <Space wrap>
                  <Button icon={<EditOutlined />} onClick={() => openEdit(room)}>
                    编辑
                  </Button>
                  <Button type="primary" disabled={active} loading={actionKey === `start:${room.id}`} onClick={() => startRoom(room)}>
                    开始
                  </Button>
                  <Button danger disabled={!active} loading={actionKey === `stop:${room.id}`} onClick={() => stopRoom(room)}>
                    停止
                  </Button>
                  <Popconfirm
                    title="删除直播间"
                    description={active ? '录制中的直播间不能删除，请先停止录制。' : '删除后会从直播间列表移除，历史任务和文件不会被物理删除。'}
                    okText="删除"
                    cancelText="取消"
                    disabled={active}
                    onConfirm={() => deleteRoom(room)}
                  >
                    <Button danger icon={<DeleteOutlined />} disabled={active} loading={actionKey === `delete:${room.id}`}>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              )
            },
          },
        ]}
      />

      <Drawer title={editingRoom ? '编辑直播间' : '新增直播间'} width={440} open={drawerOpen} onClose={() => setDrawerOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={saveRoom} initialValues={{ quality: '原画', enabled: true }}>
          <Form.Item name="url" label="直播间链接" rules={[{ required: true, message: '请输入直播间链接' }]}>
            <Input placeholder="https://live.douyin.com/..." />
          </Form.Item>
          <Form.Item name="name" label="主播名">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="quality" label="清晰度">
            <Select options={qualityOptions.map((quality) => ({ label: quality, value: quality }))} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saving} block>
            保存
          </Button>
        </Form>
      </Drawer>
    </div>
  )
}

export default Rooms
