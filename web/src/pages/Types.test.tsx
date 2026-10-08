import {cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import {Types} from './Types'
vi.mock('../lib/api',async original=>({...await original<typeof import('../lib/api')>(),gql:vi.fn(async()=>({entries:{nodes:[]},assets:[]}))}))
afterEach(cleanup)
test('form preview edits stay local and survive presentation flag changes',()=>{
 render(<Types types={[]} role="admin" onChanged={vi.fn()} />)
 fireEvent.click(screen.getByRole('button',{name:'New type'}))
 const preview=screen.getByRole('complementary',{name:'Content type previews'})
 const title=preview.querySelector('input')!
 fireEvent.change(title,{target:{value:'Local preview'}})
 expect(title.value).toBe('Local preview')
 expect(screen.getByText(/private fields are hidden/)).toBeTruthy()
})
