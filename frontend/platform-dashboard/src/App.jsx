import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { LocaleProvider } from '@douyinfe/semi-ui';
import zh_CN from '@douyinfe/semi-ui/lib/es/locale/source/zh_CN';
import { ToastContainer } from 'react-toastify';
import Dashboard from './components/dashboard';
import { UserContext } from './context/User';
import { reducer as userReducer } from './context/User/reducer';
import { StatusContext } from './context/Status';
import { reducer as statusReducer } from './context/Status/reducer';

export default function App({ bootstrap }) {
  const [userState, userDispatch] = React.useReducer(userReducer, {
    user: bootstrap.user,
  });
  const [statusState, statusDispatch] = React.useReducer(statusReducer, {
    status: bootstrap.status,
  });

  return (
    <UserContext.Provider value={[userState, userDispatch]}>
      <StatusContext.Provider value={[statusState, statusDispatch]}>
        <BrowserRouter
          future={{
            v7_startTransition: true,
            v7_relativeSplatPath: true,
          }}
        >
          <LocaleProvider locale={zh_CN}>
            <main className='dashboard-page px-2' data-env={bootstrap.env}>
              <Dashboard />
            </main>
            <ToastContainer />
          </LocaleProvider>
        </BrowserRouter>
      </StatusContext.Provider>
    </UserContext.Provider>
  );
}
