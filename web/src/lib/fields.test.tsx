import {expect,test} from 'vitest'
import {deliveryShape,hiddenFieldCount,shapeSignature} from './fields'
import type {Field} from './api'
const fields:Field[]=[{name:'title',type:'text',localized:true},{name:'tags',type:'list',item:{name:'',type:'enum',options:['One','Two']}},{name:'group',type:'object',fields:[{name:'private',type:'text',private:true},{name:'image',type:'asset'}]},{name:'author',type:'reference'},{name:'when',type:'date'}]
test('delivery signatures match nullable generated backend names and locale arguments',()=>{
 const shape=deliveryShape('Sample','sample',fields)
 expect(shape).toContain('tags(locale: String! = "en"): [CmsSampleTagsItemEnum]')
 expect(shape).toContain('title(locale: String! = "en"): String')
 expect(shape).toContain('image(locale: String! = "en"): AssetNode')
 expect(shape).toContain('author(locale: String! = "en"): ReferenceNode')
 expect(shape).toContain('when(locale: String! = "en"): Date')
 expect(shape).toContain('id: ID!');expect(shape).not.toContain('private(')
 expect(hiddenFieldCount(fields)).toBe(1)
 expect(shapeSignature(fields)).toBe(shapeSignature(fields.map(f=>({...f,label:'Changed',required:true,private:true}))))
})
