import { signalClass } from '../lib/utils'

export default function SignalTag({ signal }) {
  if (!signal) return null
  return <span className={signalClass(signal)}>{signal.toUpperCase()}</span>
}
