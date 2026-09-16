import { useParams } from 'react-router-dom'

import { fetchMyRefundRequest } from '../api/customer'
import { StubNotice } from '../components/Async'
import { ResourceDetailPage } from '../components/ResourceDetailPage'

/** 退款申请进度 —— GET /customer/refund-requests/{request_key} */
export function CustomerRefundRequestDetailPage() {
  const { requestKey = '' } = useParams()

  return (
    <ResourceDetailPage
      title={`退款申请 ${requestKey}`}
      desc={
        <>
          来自 <code>GET /api/customer/refund-requests/{requestKey}</code>
          ：状态、审批意见、退款结果。
        </>
      }
      fetcher={() => fetchMyRefundRequest(requestKey)}
      backTo="/customer/refund-requests"
      backLabel="返回我的申请"
      notice={
        <StubNotice>
          后端尚未实现。按项目约定，<strong>「不是你的申请」和「申请不存在」必须返回完全相同的结果</strong>
          ，否则一区分就等于告诉别人「这个申请是存在的」。
        </StubNotice>
      }
    />
  )
}
